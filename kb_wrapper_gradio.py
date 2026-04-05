import os
import math
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image, ImageDraw, ImageFont
from torchvision import transforms
import gradio as gr


# =========================
# 1. MODEL ARCHITECTURE
# =========================

class FaceCNN(nn.Module):
    """CNN для классификации лиц"""

    def __init__(self, num_classes=2):
        super().__init__()

        self.conv1 = nn.Conv2d(3, 32, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm2d(32)

        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm2d(64)

        self.conv3 = nn.Conv2d(64, 128, kernel_size=3, padding=1)
        self.bn3 = nn.BatchNorm2d(128)

        self.conv4 = nn.Conv2d(128, 256, kernel_size=3, padding=1)
        self.bn4 = nn.BatchNorm2d(256)

        self.pool = nn.MaxPool2d(2, 2)
        self.dropout = nn.Dropout(0.5)

        self.fc1 = nn.Linear(256 * 8 * 8, 512)
        self.fc2 = nn.Linear(512, 128)
        self.fc3 = nn.Linear(128, num_classes)

    def forward(self, x):
        x = self.pool(F.relu(self.bn1(self.conv1(x))))
        x = self.pool(F.relu(self.bn2(self.conv2(x))))
        x = self.pool(F.relu(self.bn3(self.conv3(x))))
        x = self.pool(F.relu(self.bn4(self.conv4(x))))
        x = x.view(x.size(0), -1)

        x = self.dropout(F.relu(self.fc1(x)))
        x = self.dropout(F.relu(self.fc2(x)))
        x = self.fc3(x)
        return x


# =========================
# 2. LOAD MODEL
# =========================

def load_model(model_path: str, device: torch.device):
    model = FaceCNN(num_classes=2)

    checkpoint = torch.load(model_path, map_location=device)
    if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
        model.load_state_dict(checkpoint["model_state_dict"])
    else:
        model.load_state_dict(checkpoint)

    model.to(device)
    model.eval()
    return model


# =========================
# 3. IMAGE UTILITIES
# =========================

def build_transform(image_size: int = 128):
    return transforms.Compose([
        transforms.Resize((image_size, image_size)),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225],
        ),
    ])


def add_watermark_pil(image: Image.Image, prediction: int, confidence: float):
    """Возвращает ЧБ-изображение с большой подписью."""
    img = image.convert("RGB")
    width, height = img.size
    gray = img.convert("L").convert("RGB")
    draw = ImageDraw.Draw(gray)

    is_worker = (prediction == 0)
    label = "СОТРУДНИК КРАСНОГО И БЕЛОГО" if is_worker else "НЕ СОТРУДНИК КРАСНОГО И БЕЛОГО"
    color = (255, 0, 0) if is_worker else (0, 180, 0)

    # Попытка найти шрифт посимпатичнее
    font_candidates = [
        "arial.ttf",
        "DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    font = None
    font_size = max(24, min(width, height) // 10)
    for path in font_candidates:
        try:
            font = ImageFont.truetype(path, font_size)
            break
        except Exception:
            pass
    if font is None:
        font = ImageFont.load_default()

    # Диагональная подпись
    diagonal = int(math.sqrt(width * width + height * height))
    target_width = int(diagonal * 0.72)

    # Подбор размера шрифта
    if hasattr(font, "path") or font != ImageFont.load_default():
        for size in range(font_size, 10, -2):
            try:
                trial = ImageFont.truetype(font_candidates[0], size)
            except Exception:
                try:
                    trial = ImageFont.truetype(font_candidates[1], size)
                except Exception:
                    continue
            bbox = draw.textbbox((0, 0), label, font=trial)
            text_w = bbox[2] - bbox[0]
            if text_w <= target_width:
                font = trial
                break

    # Полупрозрачная плашка
    overlay = Image.new("RGBA", gray.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    pad = 16
    bbox = odraw.textbbox((0, 0), label, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    x = (width - text_w) // 2
    y = (height - text_h) // 2
    angle = -25

    # Создаем отдельный слой текста и поворачиваем
    txt_layer = Image.new("RGBA", gray.size, (0, 0, 0, 0))
    tdraw = ImageDraw.Draw(txt_layer)
    tdraw.rectangle(
        [x - pad, y - pad, x + text_w + pad, y + text_h + pad],
        fill=(0, 0, 0, 90),
    )
    tdraw.text((x, y), label, font=font, fill=color + (255,))

    txt_layer = txt_layer.rotate(angle, resample=Image.Resampling.BICUBIC, center=(width // 2, height // 2))
    overlay = Image.alpha_composite(overlay, txt_layer)
    result = Image.alpha_composite(gray.convert("RGBA"), overlay).convert("RGB")
    return result


def predict_and_mark_pil(model, image: Image.Image, device: torch.device, image_size: int = 128):
    transform = build_transform(image_size=image_size)
    image_rgb = image.convert("RGB")
    tensor = transform(image_rgb).unsqueeze(0).to(device)

    with torch.no_grad():
        outputs = model(tensor)
        probs = F.softmax(outputs, dim=1)
        confidence, predicted = torch.max(probs, 1)

    pred_class = int(predicted.item())
    conf_value = float(confidence.item())
    marked = add_watermark_pil(image_rgb, pred_class, conf_value)

    label = "СОТРУДНИК КРАСНОГО И БЕЛОГО" if pred_class == 0 else "НЕ СОТРУДНИК КРАСНОГО И БЕЛОГО"
    return marked, label, conf_value


# =========================
# 4. GRADIO APP
# =========================

MODEL_PATH = "face_classifier.pth"   # положи веса рядом с этим файлом
IMAGE_SIZE = 128

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = None

if os.path.exists(MODEL_PATH):
    model = load_model(MODEL_PATH, device)
else:
    print(f"Файл модели не найден: {MODEL_PATH}")

def infer(image):
    if model is None:
        raise gr.Error(f"Не найден файл весов модели: {MODEL_PATH}")

    if image is None:
        raise gr.Error("Сначала загрузите фотографию.")

    marked, label, confidence = predict_and_mark_pil(model, image, device, image_size=IMAGE_SIZE)
    info = f"{label} | уверенность: {confidence * 100:.1f}%"
    return marked, info

with gr.Blocks(title="Проверка сотрудника КБ") as demo:
    gr.Markdown("## Проверка сотрудника Красного и Белого")
    gr.Markdown("Загрузите фото, и модель вернёт чёрно-белую версию с подписью.")

    with gr.Row():
        inp = gr.Image(type="pil", label="Фотография")
        out = gr.Image(type="pil", label="Результат")

    status = gr.Textbox(label="Статус", interactive=False)
    btn = gr.Button("Проверить")

    btn.click(fn=infer, inputs=inp, outputs=[out, status])

if __name__ == "__main__":
    demo.launch()