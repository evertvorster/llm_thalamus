import cv2
import numpy as np

# Load the image
image_path = 'test_sd15_diag.png'
image = cv2.imread(image_path)

if image is None:
    print("Error: Image not found.")
else:
    # Display the image
    cv2.imshow('Image', image)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    # Perform some basic analysis (e.g., get dimensions, show histogram, etc.)
    height, width, channels = image.shape
    print(f"Image Dimensions: {width}x{height}")
    print(f"Number of Channels: {channels}")

    # Convert to grayscale and display
    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    cv2.imshow('Grayscale Image', gray_image)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    # Compute histogram for one channel (e.g., red channel)
    hist = cv2.calcHist([gray_image], [0], None, [256], [0, 256])
    import matplotlib.pyplot as plt
    plt.plot(hist)
    plt.show()
