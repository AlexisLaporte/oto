"""Gemini image generation commands."""

import typer
from typing import Optional
from pathlib import Path

app = typer.Typer(help="Gemini image generation (text-to-image and image editing)")

MODEL_ALIASES = {
    "flash": "gemini-2.5-flash-image",
    "flash2": "gemini-3.1-flash-image-preview",
    "pro": "gemini-3-pro-image-preview",
}


def resolve_model(model: str) -> str:
    return MODEL_ALIASES.get(model, model)


@app.command("generate")
def generate(
    prompt: str = typer.Option(..., "--prompt", "-p", help="Generation prompt"),
    image: Optional[str] = typer.Option(None, "--image", "-i", help="Source image path (for editing/compositing)"),
    output: str = typer.Option("output.jpg", "--output", "-o", help="Output file path"),
    model: str = typer.Option("flash", "--model", "-m", help="Model: flash, flash2, pro, or full model ID"),
    size: Optional[str] = typer.Option(None, "--size", "-s", help="Output size (e.g. 2K). Pro model only."),
):
    """Generate or edit an image via Gemini."""
    import json
    import base64
    import mimetypes
    from oto.tools.gemini import GeminiClient

    client = GeminiClient()
    resolved = resolve_model(model)
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if image:
        # Image editing mode: send source image + prompt
        src = Path(image)
        if not src.exists():
            print(json.dumps({"status": "error", "error": f"Image not found: {image}"}))
            raise typer.Exit(1)
        mime = mimetypes.guess_type(str(src))[0] or "image/jpeg"
        b64 = base64.b64encode(src.read_bytes()).decode()
        result = client.edit_image(prompt, b64, mime, model=resolved, image_size=size)
        if result["status"] == "success":
            img_bytes = base64.b64decode(result["data"])
            out_path.write_bytes(img_bytes)
            print(json.dumps({"status": "success", "output": str(out_path), "model": resolved}))
        else:
            print(json.dumps(result))
            raise typer.Exit(1)
    else:
        # Text-to-image mode
        result = client.generate_image(prompt, output_dir=str(out_path.parent), model=resolved)
        if result["status"] == "success":
            # Rename to requested output path
            generated = Path(result["image_path"])
            if generated != out_path:
                generated.rename(out_path)
            print(json.dumps({"status": "success", "output": str(out_path), "model": resolved}))
        else:
            print(json.dumps(result))
            raise typer.Exit(1)


@app.command("batch")
def batch(
    manifest: str = typer.Option(..., "--manifest", "-f", help="JSON manifest file path"),
    output_dir: str = typer.Option(".", "--output-dir", "-d", help="Output directory"),
    model: str = typer.Option("flash", "--model", "-m", help="Default model (overridable per job)"),
    size: Optional[str] = typer.Option(None, "--size", "-s", help="Output size (e.g. 2K)"),
    skip_existing: bool = typer.Option(True, "--skip-existing/--no-skip", help="Skip if output file exists"),
    delay: float = typer.Option(2.0, "--delay", help="Seconds between API calls"),
):
    """Batch generate images from a JSON manifest.

    Manifest format: array of objects with keys:
      - prompt (required): generation prompt
      - image (optional): source image path
      - output (required): output filename
      - model (optional): override model for this job
    """
    import json
    import time
    import base64
    import mimetypes
    from oto.tools.gemini import GeminiClient

    manifest_path = Path(manifest)
    if not manifest_path.exists():
        print(json.dumps({"status": "error", "error": f"Manifest not found: {manifest}"}))
        raise typer.Exit(1)

    jobs = json.loads(manifest_path.read_text())
    if not isinstance(jobs, list):
        print(json.dumps({"status": "error", "error": "Manifest must be a JSON array"}))
        raise typer.Exit(1)

    client = GeminiClient()
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    default_model = resolve_model(model)

    results = []
    for i, job in enumerate(jobs):
        out_file = out_dir / job["output"]
        job_model = resolve_model(job.get("model", model))

        if skip_existing and out_file.exists():
            results.append({"output": job["output"], "status": "skipped"})
            continue

        out_file.parent.mkdir(parents=True, exist_ok=True)
        source = job.get("image")

        try:
            if source:
                src = Path(source)
                if not src.exists():
                    results.append({"output": job["output"], "status": "error", "error": f"Image not found: {source}"})
                    continue
                mime = mimetypes.guess_type(str(src))[0] or "image/jpeg"
                b64 = base64.b64encode(src.read_bytes()).decode()
                result = client.edit_image(job["prompt"], b64, mime, model=job_model, image_size=size)
                if result["status"] == "success":
                    out_file.write_bytes(base64.b64decode(result["data"]))
                    results.append({"output": job["output"], "status": "success", "model": job_model})
                else:
                    results.append({"output": job["output"], "status": "error", "error": result.get("error", "")})
            else:
                result = client.generate_image(job["prompt"], output_dir=str(out_file.parent), model=job_model)
                if result["status"] == "success":
                    generated = Path(result["image_path"])
                    if generated != out_file:
                        generated.rename(out_file)
                    results.append({"output": job["output"], "status": "success", "model": job_model})
                else:
                    results.append({"output": job["output"], "status": "error", "error": result.get("error", "")})
        except Exception as e:
            results.append({"output": job["output"], "status": "error", "error": str(e)})

        # Progress
        done = sum(1 for r in results if r["status"] == "success")
        skipped = sum(1 for r in results if r["status"] == "skipped")
        errors = sum(1 for r in results if r["status"] == "error")
        print(f"[{i+1}/{len(jobs)}] {job['output']} → {results[-1]['status']}  (done={done} skip={skipped} err={errors})", flush=True)

        if i < len(jobs) - 1 and results[-1]["status"] != "skipped":
            time.sleep(delay)

    # Summary
    summary = {
        "total": len(jobs),
        "success": sum(1 for r in results if r["status"] == "success"),
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
        "errors": sum(1 for r in results if r["status"] == "error"),
    }
    print(json.dumps({"summary": summary, "results": results}, indent=2, ensure_ascii=False))
