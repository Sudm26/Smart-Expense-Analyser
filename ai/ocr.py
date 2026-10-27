"""Receipt-specific image preprocessing and OCR using EasyOCR."""
from pathlib import Path

_reader = None


def _resize_for_ocr(image, maximum_side: int = 2200):
    """Keep OCR fast and consistent on multi-megapixel phone photos."""
    import cv2

    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= maximum_side:
        return image
    scale = maximum_side / longest
    return cv2.resize(image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)


def _order_corners(points):
    """Return corners in top-left, top-right, bottom-right, bottom-left order."""
    import numpy as np

    ordered = np.zeros((4, 2), dtype="float32")
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).ravel()
    ordered[0], ordered[2] = points[sums.argmin()], points[sums.argmax()]
    ordered[1], ordered[3] = points[differences.argmin()], points[differences.argmax()]
    return ordered


def _crop_receipt(image):
    """Perspective-crop the largest document-shaped contour when reliable."""
    import cv2
    import numpy as np

    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        if cv2.contourArea(contour) < height * width * 0.20:
            break
        corners = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
        if len(corners) != 4:
            continue
        points = _order_corners(corners.reshape(4, 2).astype("float32"))
        output_width = max(int(np.linalg.norm(points[1] - points[0])), int(np.linalg.norm(points[2] - points[3])))
        output_height = max(int(np.linalg.norm(points[3] - points[0])), int(np.linalg.norm(points[2] - points[1])))
        if output_width < 80 or output_height < 80:
            continue
        destination = np.float32([[0, 0], [output_width - 1, 0], [output_width - 1, output_height - 1], [0, output_height - 1]])
        return cv2.warpPerspective(image, cv2.getPerspectiveTransform(points, destination), (output_width, output_height))
    return image  # Scans/screenshots may not have visible paper edges.


def _straighten(gray):
    """Deskew mild rotation from text pixels; ignore unrealistic estimates."""
    import cv2
    import numpy as np

    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coordinates = np.column_stack(np.where(binary > 0))
    if len(coordinates) < 100:
        return gray
    angle = cv2.minAreaRect(coordinates)[-1]
    angle = -(90 + angle) if angle < -45 else -angle
    if not 0.4 <= abs(angle) <= 12:
        return gray
    height, width = gray.shape[:2]
    matrix = cv2.getRotationMatrix2D((width // 2, height // 2), angle, 1.0)
    return cv2.warpAffine(gray, matrix, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _prepare_receipt_images(image_path: Path):
    """Return thresholded and natural-looking enhanced OCR variants."""
    import cv2

    image = cv2.imread(str(image_path))
    if image is None:
        return None, None
    gray = cv2.cvtColor(_resize_for_ocr(_crop_receipt(image)), cv2.COLOR_BGR2GRAY)
    gray = _straighten(gray)
    denoised = cv2.fastNlMeansDenoising(gray, None, h=8, templateWindowSize=7, searchWindowSize=21)
    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(denoised)
    enlarged = cv2.resize(enhanced, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
    enlarged = _resize_for_ocr(enlarged)
    thresholded = cv2.adaptiveThreshold(enlarged, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11)
    return thresholded, enlarged


def preprocess_receipt(image_path: Path):
    """Compatibility wrapper returning the thresholded receipt image."""
    thresholded, _ = _prepare_receipt_images(image_path)
    return thresholded


def _read_blocks(reader, image, source: str):
    """Read OCR blocks while retaining their location and recognition confidence."""
    height, width = image.shape[:2]
    # Contrast adjustment helps with thermal paper, shadows, and slightly faded ink
    # without needing a receipt-specific trained model.
    results = reader.readtext(
        image,
        detail=1,
        paragraph=False,
        mag_ratio=1,
        canvas_size=2200,
        contrast_ths=0.05,
        adjust_contrast=0.7,
    )
    blocks = []
    for box, text, confidence in results:
        if confidence < 0.30 or not text.strip():
            continue
        top = min(point[1] for point in box)
        left = min(point[0] for point in box)
        bottom = max(point[1] for point in box)
        right = max(point[0] for point in box)
        blocks.append(
            {
                "text": text.strip(),
                "confidence": float(confidence),
                "top_ratio": float(top / height),
                "bottom_ratio": float(bottom / height),
                "left_ratio": float(left / width),
                "right_ratio": float(right / width),
                "height_ratio": float((bottom - top) / height),
                "source": source,
            }
        )
    return blocks


def read_receipt(image_path: Path) -> tuple[str, str, list[dict]]:
    global _reader
    try:
        import easyocr
    except ImportError:
        return "", "OCR is not installed yet. Enter the fields manually, or install EasyOCR.", []
    try:
        import cv2

        prepared, clarity = _prepare_receipt_images(image_path)
        if prepared is None:
            return "", "The uploaded image could not be opened. Please upload it again.", []
        if _reader is None:
            _reader = easyocr.Reader(["en"], gpu=False)
        original = cv2.imread(str(image_path))
        processed_blocks = _read_blocks(_reader, prepared, "enhanced")
        clarity_blocks = _read_blocks(_reader, clarity, "clarity")
        original_blocks = _read_blocks(_reader, _resize_for_ocr(original), "original") if original is not None else []
        # Enhanced OCR is usually strongest for amounts/items. Original OCR is retained
        # because logos and prominent merchant headings can be clearer before thresholding.
        ocr_text = "\n".join(block["text"] for block in processed_blocks)
        all_blocks = processed_blocks + clarity_blocks + original_blocks
        message = "OCR completed using original, contrast-enhanced, and thresholded receipt images. Please review the extracted values."
        return ocr_text, message, all_blocks
    except Exception as error:
        return "", f"OCR could not read this receipt: {error}. You can enter the details manually.", []
