"""Method illustration diagram generator for AutoR.

Adapts the PaperBanana multi-agent pipeline (Planner → Stylist → Visualizer → Critic)
into a self-contained module that generates method illustration diagrams using the
Gemini API and inserts them into the LaTeX paper.

API keys are read from environment variables or a config file that is gitignored.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from io import BytesIO
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Lazy imports – these are only needed when diagram generation is active
# ---------------------------------------------------------------------------

_gemini_client = None


def _get_gemini_client():
    """Return a cached Gemini client, initialising on first call."""
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client

    from google import genai

    api_key = _resolve_api_key()
    if not api_key:
        raise RuntimeError(
            "Gemini API key not found. Set GOOGLE_API_KEY or GEMINI_API_KEY "
            "in environment, or create configs/diagram_config.yaml (see template)."
        )
    _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def _resolve_api_key() -> str | None:
    """Resolve Gemini API key from env vars or config file (never hardcoded)."""
    for env_var in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
        val = os.environ.get(env_var, "").strip()
        if val:
            return val

    config_path = Path(__file__).resolve().parent.parent / "configs" / "diagram_config.yaml"
    if config_path.exists():
        import yaml
        with open(config_path, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
        api_keys = cfg.get("api_keys", {})
        for key_name in ("google_api_key", "gemini_api_key"):
            val = (api_keys.get(key_name) or "").strip()
            if val:
                return val
    return None


# ---------------------------------------------------------------------------
# Style guide (embedded subset of PaperBanana NeurIPS 2025 diagram guide)
# ---------------------------------------------------------------------------

NEURIPS_STYLE_GUIDE = """\
## NeurIPS 2025 Diagram Style Guide (Condensed)

### Aesthetic: "Soft Tech & Scientific Pastels"
- Use very light, desaturated pastel backgrounds (opacity 10-15%).
  - Cream (#F5F5DC), Pale Blue (#E6F3FF), Mint (#E0F2F1), Lavender (#F3E5F5).
- Reserve saturated color for active/highlight elements.
- Trainable elements → warm tones (red, orange); Frozen → cool tones (grey, ice blue).

### Shapes
- Process nodes: Rounded rectangles (radius 5-10px). Dominant shape (~80%).
- Tensors/data: 3D cuboids for volume, flat grids for matrices, cylinders for memory.
- Dashed borders for logical stages or optional paths.

### Lines & Arrows
- Orthogonal/elbow for architecture flow; curved for high-level logic.
- Solid for data flow; dashed for auxiliary (gradients, skip connections).
- Place math operators (⊕, ⊗) directly on lines.

### Typography
- Labels: Sans-serif (Arial, Roboto). Bold for headers.
- Math variables: Serif, italicised.

### Icons
- Trainable: fire/lightning. Frozen: snowflake/padlock.
- Text: document/chat bubble. Image: actual thumbnail.

### Avoid
- PowerPoint defaults, font mixing, inconsistent 2D/3D, saturated backgrounds.
"""


# ---------------------------------------------------------------------------
# Agent prompts (adapted from PaperBanana)
# ---------------------------------------------------------------------------

PLANNER_SYSTEM_PROMPT = """\
You are an expert at describing scientific diagrams for AI papers.

Given the methodology section of a paper and a figure caption, produce a VERY DETAILED
textual description of an illustrative diagram. Include:
- Every component (boxes, arrows, labels, icons).
- Layout and spatial arrangement (left-to-right, top-to-bottom).
- Background style (typically pure white or very light pastel).
- Colours (specific hex codes), line thickness, icon styles.
- Connections and data flow between components.

Be as specific as possible. Vague descriptions produce poor figures.
Do NOT include figure titles or captions inside the diagram itself.
Output ONLY the description text.
"""

STYLIST_SYSTEM_PROMPT = """\
You are a Lead Visual Designer for NeurIPS 2025.

Refine and enrich the preliminary diagram description to meet publication-ready
NeurIPS 2025 aesthetic standards. Follow the provided style guidelines.

Rules:
1. Preserve semantic content and logic — only refine aesthetics.
2. If description already looks high-quality, preserve it.
3. Enrich plain descriptions with specific visual attributes (hex colours, fonts, line widths).
4. Handle icons carefully — preserve semantic meaning (snowflake=frozen, fire=trainable).
5. Do NOT rewrite from scratch; enhance what exists.

Output ONLY the final polished description. No explanations.
"""

VISUALIZER_SYSTEM_PROMPT = (
    "You are an expert scientific diagram illustrator. "
    "Generate high-quality scientific diagrams based on user requests."
)

CRITIC_SYSTEM_PROMPT = """\
You are a Lead Visual Designer for NeurIPS 2025.

Critique the diagram based on content fidelity and presentation quality.
Check:
1. Content: alignment with methodology, text accuracy, no hallucinated content, no caption in image.
2. Presentation: clarity, readability, no redundant legends.

Output strictly in this JSON format:
```json
{
    "critic_suggestions": "Your critique or 'No changes needed.'",
    "revised_description": "Revised description or 'No changes needed.'"
}
```
"""


# ---------------------------------------------------------------------------
# Core pipeline functions
# ---------------------------------------------------------------------------

async def _call_gemini_text(
    prompt_parts: list[dict[str, Any]],
    system_prompt: str,
    model_name: str = "gemini-2.5-flash",
) -> str:
    """Call Gemini text generation with retry."""
    from google.genai import types

    client = _get_gemini_client()
    gemini_parts = []
    for item in prompt_parts:
        if item.get("type") == "text":
            gemini_parts.append(types.Part.from_text(text=item["text"]))
        elif item.get("type") == "image_bytes":
            gemini_parts.append(
                types.Part.from_bytes(
                    data=base64.b64decode(item["data"]),
                    mime_type=item.get("mime_type", "image/jpeg"),
                )
            )

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=1.0,
        candidate_count=1,
        max_output_tokens=50000,
    )

    for attempt in range(5):
        try:
            response = await client.aio.models.generate_content(
                model=model_name, contents=gemini_parts, config=config,
            )
            text = response.candidates[0].content.parts[0].text
            if text and text.strip():
                return text.strip()
        except Exception as exc:
            delay = min(5 * (2 ** attempt), 30)
            print(f"[diagram_gen] text attempt {attempt+1} failed: {exc}, retrying in {delay}s")
            await asyncio.sleep(delay)
    return ""


async def _call_gemini_image(
    prompt_text: str,
    system_prompt: str = "",
    model_name: str = "gemini-3.1-flash-image-preview",
) -> str | None:
    """Call Gemini image generation, return base64 JPEG or None.

    Supports both Imagen 4 (generate_images API) and Gemini native image
    generation (generate_content with response_modalities=IMAGE).
    """
    from google.genai import types

    client = _get_gemini_client()
    is_imagen = "imagen" in model_name

    for attempt in range(5):
        try:
            if is_imagen:
                response = await client.aio.models.generate_images(
                    model=model_name,
                    prompt=prompt_text,
                    config=types.GenerateImagesConfig(number_of_images=1),
                )
                if response.generated_images:
                    raw = base64.b64encode(
                        response.generated_images[0].image.image_bytes
                    ).decode("utf-8")
                    return _convert_to_jpeg_b64(raw)
            else:
                parts = [types.Part.from_text(text=prompt_text)]
                config = types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                )
                response = await client.aio.models.generate_content(
                    model=model_name, contents=parts, config=config,
                )
                if response.candidates and response.candidates[0].content.parts:
                    for part in response.candidates[0].content.parts:
                        if part.inline_data:
                            raw = base64.b64encode(part.inline_data.data).decode("utf-8")
                            return _convert_to_jpeg_b64(raw)
        except Exception as exc:
            delay = min(5 * (2 ** attempt), 30)
            print(f"[diagram_gen] image attempt {attempt+1} failed: {exc}, retrying in {delay}s")
            await asyncio.sleep(delay)
    return None


def _convert_to_jpeg_b64(b64_data: str) -> str:
    """Convert any image format to JPEG base64."""
    try:
        from PIL import Image
        raw = base64.b64decode(b64_data)
        img = Image.open(BytesIO(raw))
        if img.mode in ("RGBA", "P", "LA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=95)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        return b64_data


# ---------------------------------------------------------------------------
# High-level pipeline
# ---------------------------------------------------------------------------

async def generate_method_diagram(
    method_text: str,
    figure_caption: str,
    output_path: Path,
    model_name: str = "gemini-2.5-flash",
    image_model_name: str = "gemini-3.1-flash-image-preview",
    max_critic_rounds: int = 2,
) -> Path | None:
    """Run the full Planner → Stylist → Visualizer → Critic pipeline.

    Parameters
    ----------
    method_text : str
        The methodology section of the paper.
    figure_caption : str
        Caption for the method illustration figure.
    output_path : Path
        Where to save the final JPEG image.
    model_name : str
        Gemini model to use for text reasoning.
    image_model_name : str
        Gemini model to use for image generation.
    max_critic_rounds : int
        Maximum critic-visualiser iteration rounds.

    Returns
    -------
    Path or None
        Path to the saved image, or None on failure.
    """
    print("[diagram_gen] Step 1/4: Planner — generating diagram description...")
    planner_prompt = [
        {"type": "text", "text": (
            f"Methodology Section:\n{method_text}\n\n"
            f"Figure Caption:\n{figure_caption}\n\n"
            "Provide a detailed description of the target diagram (do not include figure titles):"
        )}
    ]
    description = await _call_gemini_text(planner_prompt, PLANNER_SYSTEM_PROMPT, model_name)
    if not description:
        print("[diagram_gen] Planner failed to produce description.")
        return None

    print("[diagram_gen] Step 2/4: Stylist — refining aesthetics...")
    stylist_prompt = [
        {"type": "text", "text": (
            f"Detailed Description:\n{description}\n\n"
            f"Style Guidelines:\n{NEURIPS_STYLE_GUIDE}\n\n"
            f"Methodology Section:\n{method_text}\n\n"
            f"Diagram Caption:\n{figure_caption}\n\n"
            "Your Output:"
        )}
    ]
    styled_desc = await _call_gemini_text(stylist_prompt, STYLIST_SYSTEM_PROMPT, model_name)
    if not styled_desc:
        styled_desc = description  # fallback to planner output

    print("[diagram_gen] Step 3/4: Visualiser — generating image...")
    vis_prompt = (
        f"Render an image based on the following detailed description: {styled_desc}\n"
        "Note that do not include figure titles in the image. Diagram:"
    )
    image_b64 = await _call_gemini_image(
        vis_prompt, VISUALIZER_SYSTEM_PROMPT, image_model_name,
    )
    if not image_b64:
        print("[diagram_gen] Visualiser failed to generate image.")
        return None

    # Critic loop
    current_desc = styled_desc
    current_image = image_b64
    for round_idx in range(max_critic_rounds):
        print(f"[diagram_gen] Step 4/4: Critic — round {round_idx + 1}/{max_critic_rounds}...")
        critic_parts = [
            {"type": "text", "text": "Target Diagram for Critique:"},
            {"type": "image_bytes", "data": current_image, "mime_type": "image/jpeg"},
            {"type": "text", "text": (
                f"Detailed Description:\n{current_desc}\n\n"
                f"Methodology Section:\n{method_text}\n\n"
                f"Figure Caption:\n{figure_caption}\n\n"
                "Your Output:"
            )},
        ]
        critic_raw = await _call_gemini_text(critic_parts, CRITIC_SYSTEM_PROMPT, model_name)

        # Parse JSON response
        cleaned = critic_raw.replace("```json", "").replace("```", "").strip()
        try:
            import json_repair
            result = json_repair.loads(cleaned)
        except Exception:
            try:
                result = json.loads(cleaned)
            except Exception:
                result = {}

        suggestions = result.get("critic_suggestions", "No changes needed.")
        revised = result.get("revised_description", "No changes needed.")

        if suggestions.strip() == "No changes needed." or revised.strip() == "No changes needed.":
            print(f"[diagram_gen] Critic round {round_idx + 1}: no changes needed.")
            break

        # Re-visualise with revised description
        current_desc = revised
        new_prompt = (
            f"Render an image based on the following detailed description: {current_desc}\n"
            "Note that do not include figure titles in the image. Diagram:"
        )
        new_image = await _call_gemini_image(
            new_prompt, VISUALIZER_SYSTEM_PROMPT, image_model_name,
        )
        if new_image:
            current_image = new_image
            print(f"[diagram_gen] Critic round {round_idx + 1}: re-visualised successfully.")
        else:
            print(f"[diagram_gen] Critic round {round_idx + 1}: re-visualisation failed, keeping previous.")
            break

    # Save final image
    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_bytes = base64.b64decode(current_image)
    output_path.write_bytes(raw_bytes)
    print(f"[diagram_gen] Saved method illustration to {output_path}")
    return output_path


def generate_method_diagram_sync(
    method_text: str,
    figure_caption: str,
    output_path: Path,
    model_name: str = "gemini-2.5-flash",
    image_model_name: str = "gemini-3.1-flash-image-preview",
    max_critic_rounds: int = 2,
) -> Path | None:
    """Synchronous wrapper for generate_method_diagram."""
    return asyncio.run(generate_method_diagram(
        method_text=method_text,
        figure_caption=figure_caption,
        output_path=output_path,
        model_name=model_name,
        image_model_name=image_model_name,
        max_critic_rounds=max_critic_rounds,
    ))


# ---------------------------------------------------------------------------
# LaTeX integration helpers
# ---------------------------------------------------------------------------

METHOD_FIGURE_LATEX = r"""
\begin{{figure*}}[t]
    \centering
    \includegraphics[width=0.95\textwidth]{{{image_path}}}
    \caption{{{caption}}}
    \label{{fig:method_overview}}
\end{{figure*}}
"""


def inject_diagram_into_latex(
    method_tex_path: Path,
    image_rel_path: str,
    caption: str,
) -> bool:
    """Insert a method illustration figure at the top of method.tex.

    Returns True if the figure was inserted, False if it already exists or the
    file could not be read.
    """
    if not method_tex_path.exists():
        return False

    content = method_tex_path.read_text(encoding="utf-8")

    # Don't insert twice
    if "fig:method_overview" in content:
        return False

    figure_block = METHOD_FIGURE_LATEX.format(
        image_path=image_rel_path,
        caption=caption,
    ).strip()

    # Insert after the first \section or at the top
    import re
    section_match = re.search(r"(\\section\{[^}]*\}\s*(?:\\label\{[^}]*\}\s*)?)", content)
    if section_match:
        insert_pos = section_match.end()
        new_content = content[:insert_pos] + "\n\n" + figure_block + "\n\n" + content[insert_pos:]
    else:
        new_content = figure_block + "\n\n" + content

    method_tex_path.write_text(new_content, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Post-writing hook: extract method text and generate diagram
# ---------------------------------------------------------------------------

def post_writing_diagram_hook(run_root: Path, model_name: str = "gemini-2.5-flash") -> Path | None:
    """After Stage 07 writing, extract method.tex content and generate a diagram.

    This reads the already-written method.tex, generates an illustration, saves it
    to the figures directory, and injects the figure reference into method.tex.
    """
    workspace = run_root / "workspace"
    method_tex = workspace / "writing" / "sections" / "method.tex"
    figures_dir = workspace / "figures"
    output_image = figures_dir / "method_overview.jpg"

    # Read method section text
    if not method_tex.exists():
        print("[diagram_gen] method.tex not found, skipping diagram generation.")
        return None

    method_text = method_tex.read_text(encoding="utf-8")
    if len(method_text.strip()) < 100:
        print("[diagram_gen] method.tex too short, skipping diagram generation.")
        return None

    # Also try to read the memory for a richer understanding
    memory_path = run_root / "memory.md"
    memory_snippet = ""
    if memory_path.exists():
        full_memory = memory_path.read_text(encoding="utf-8")
        # Extract the hypothesis and study design sections for context
        for section_name in ["Hypothesis Generation", "Study Design", "Implementation"]:
            idx = full_memory.find(section_name)
            if idx >= 0:
                end_idx = full_memory.find("\n# Stage", idx + 1)
                if end_idx < 0:
                    end_idx = min(idx + 3000, len(full_memory))
                memory_snippet += full_memory[idx:end_idx] + "\n\n"

    combined_method = method_text
    if memory_snippet:
        combined_method = (
            "## Context from earlier research stages:\n"
            + memory_snippet[:4000]
            + "\n\n## LaTeX method section:\n"
            + method_text
        )

    caption = (
        "Overview of the proposed method. "
        "The diagram illustrates the key components and data flow of our approach."
    )

    result = generate_method_diagram_sync(
        method_text=combined_method,
        figure_caption=caption,
        output_path=output_image,
        model_name=model_name,
    )

    if result is None:
        return None

    # Inject into method.tex
    # Use relative path from writing/ directory
    image_rel = "../figures/method_overview.jpg"
    injected = inject_diagram_into_latex(method_tex, image_rel, caption)
    if injected:
        print("[diagram_gen] Injected figure reference into method.tex")
    else:
        print("[diagram_gen] Figure reference already exists or could not be injected.")

    return result
