import cv2
import pytesseract

def process_image(image_path):
    # Load the image
    img = cv2.imread(image_path)
    
    # Convert to grayscale for OCR (pytesseract requires this format)
    gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Use OCR to extract text from the image
    text = pytesseract.image_to_string(gray_img)
    
    print("OCR Text:")
    print(text)

    # Additional processing: detect and describe objects in the scene
    # Note: This step requires an object detection model, which is not part of OpenCV or pytesseract.
    # For now, we'll just print a placeholder for this functionality.
    print("\nScene Description (Placeholder):")
    print("This function would use additional tools like YOLO, SSD, etc., to describe objects in the image.")

# Example usage
image_path = "test_sd15_diag.png"
process_image(image_path)
