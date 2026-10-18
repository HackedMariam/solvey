import os
import json
import spaces
import torch
import gradio as gr
from huggingface_hub import login
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration
from peft import PeftModel

BASE_ID = "Qwen/Qwen2.5-VL-3B-Instruct"
ADAPTER = "HackedM/solvey-qwen2.5-vl-3b-lora"
HF_TOKEN = os.environ.get("HF_TOKEN")
if HF_TOKEN:
    login(token=HF_TOKEN)

SYSTEM_PROMPT = """You are Solvey's intake evidence extractor. You receive a screenshot of an IT support problem and the user's text description. Both may be present.

Return ONLY one valid JSON object. No markdown fences, no prose.

Use this exact shape:
{
  "issue_summary": "One-sentence summary of the problem from the text and image",
  "user_reported_symptoms": ["Symptom explicitly reported by the user"],
  "environment": {"operating_system": null, "application": null, "device_type": null},
  "environment_source": "user_text|screenshot|both|unknown",
  "visual_summary": "Brief description of what is in the screenshot, or null",
  "visible_text": [{"text": "Exact readable text from the image", "type": "error_message"}],
  "observed_elements": [{"element": "Description of a relevant visual element", "state": "error"}],
  "observed_symptoms": ["Observable issue or abnormal behavior in the image"],
  "technical_details": {"error_codes": [], "network_indicators": [], "system_indicators": [], "other_details": []},
  "missing_information": ["Information the triage agent still needs"],
  "uncertainties": ["Important information that cannot be determined"],
  "visual_evidence_confidence": 0.0
}

Allowed visible_text.type values: error_message, warning, status, label, other.
Allowed observed_elements.state values: error, warning, active, inactive, disconnected, unknown.
Allowed environment_source values: user_text, screenshot, both, unknown.

Rules:
- Use both the user text and the screenshot. They describe the same issue.
- issue_summary: combine the user text and the image into one factual sentence. Do not diagnose.
- user_reported_symptoms: only symptoms the user explicitly writes. Do not infer.
- visual_summary, visible_text, observed_elements, observed_symptoms, technical_details: screenshot only.
- visible_text must come from the image only. Do not copy the user's text into visible_text.
- Transcribe visible text exactly; do not invent, correct, or translate it.
- Choose one allowed enum value. Never output "error_message|warning|status|label|other" as a literal.
- environment: fill from the user text or the screenshot. Set environment_source to where it came from.
- missing_information: list what the triage agent still needs. Examples: exact error text, OS version, application name.
- Do not diagnose, explain, or recommend fixes. Do not use first-person language.
- observed_symptoms must be observable behavior, not a diagnosis.
- If there is no image: set visual_summary to null, all visual arrays to [], visual_evidence_confidence to 0.0, and add "No screenshot provided." to uncertainties. Still fill issue_summary and user_reported_symptoms from the text.
- If there is no text: set user_reported_symptoms to [] and still describe the image.
- If text and image disagree, report both and add the conflict to uncertainties.
- visual_evidence_confidence: 0.0 = no image; 0.1-0.3 = mostly unreadable; 0.4-0.6 = partial; 0.7-0.9 = clear with minor gaps; 1.0 = fully readable and complete.
"""


def empty_evidence():
    return {
        "issue_summary": "",
        "user_reported_symptoms": [],
        "environment": {"operating_system": None, "application": None, "device_type": None},
        "environment_source": "unknown",
        "visual_summary": None,
        "visible_text": [],
        "observed_elements": [],
        "observed_symptoms": [],
        "technical_details": {"error_codes": [], "network_indicators": [], "system_indicators": [], "other_details": []},
        "missing_information": [],
        "uncertainties": [],
        "visual_evidence_confidence": 0.0,
    }


processor = AutoProcessor.from_pretrained(
    ADAPTER,
    min_pixels=64 * 28 * 28,
    max_pixels=512 * 28 * 28,
)

base = Qwen2_5_VLForConditionalGeneration.from_pretrained(
    BASE_ID,
    torch_dtype=torch.bfloat16,
    attn_implementation="sdpa",
)

model = PeftModel.from_pretrained(base, ADAPTER, torch_device="cpu").to("cuda").eval()


def build_messages(text, image):
    content = []
    if image is not None:
        content.append({"type": "image"})
    content.append({"type": "text", "text": text or ""})
    return [
        {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
        {"role": "user", "content": content},
    ]


@spaces.GPU(duration=120)
def extract_gpu(text, image):
    prompt = processor.apply_chat_template(
        build_messages(text, image), tokenize=False, add_generation_prompt=True
    )
    kwargs = {"images": [image.convert("RGB")]} if image is not None else {}
    inputs = processor(
        text=[prompt],
        return_tensors="pt",
        **kwargs,
    ).to("cuda")

    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=700,
            do_sample=False,
            repetition_penalty=1.05,
        )

    raw = processor.batch_decode(
        out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True
    )[0]

    try:
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("no JSON object found in model output")
        return json.loads(raw[start:end + 1])
    except Exception as e:
        return {**empty_evidence(), "uncertainties": [f"Invalid JSON from model: {e}"]}


def ask(text, image):
    text = (text or "").strip()
    if not text and image is None:
        return {
            **empty_evidence(),
            "missing_information": ["No user text or screenshot provided."],
        }
    return extract_gpu(text, image)


with gr.Blocks(title="Solvey Intake") as demo:
    gr.Markdown("# Solvey — Intake evidence extraction")
    with gr.Row():
        image = gr.Image(type="pil", label="Screenshot (optional)")
        text = gr.Textbox(lines=6, label="Describe the problem")
    output = gr.JSON(label="Intake evidence JSON")
    btn = gr.Button("Extract evidence")
    btn.click(ask, [text, image], output)

demo.queue().launch()
