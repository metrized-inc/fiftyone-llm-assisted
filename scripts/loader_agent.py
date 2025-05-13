from smolagents import HfApiModel, CodeAgent, tool
import numpy as np
import fiftyone as fo
import fiftyone.utils.yolo as fouy
import glob
import fiftyone.brain as fob
import fiftyone.zoo as foz
import os
import cv2
from smolagents import OpenAIServerModel

# Constants
ORIGINAL_SIZE = (5760, 2840)
STRIDE = 400
CROP_SIZE = 640
RESIZE_SIZE = 640
START_ID = 1

# Parse YOLO annotations into a list of bounding boxes
def parse_yolo_annotations(filename):
    boxes = []
    with open(filename, 'r') as f:
        for line in f:
            parts = line.strip().split()
            class_id = parts[0]
            x_center, y_center, w, h = map(float, parts[1:])
            boxes.append((class_id, x_center, y_center, w, h))
    return boxes

model = OpenAIServerModel(
    model_id="gpt-4o",  # or "gpt-3.5-turbo", "gpt-4", etc.
    api_base="https://api.openai.com/v1",  # optional, defaults to OpenAI
)



def parse_yolo_annotations(filename):
    boxes = []
    with open(filename, 'r') as f:
        for line in f:
            parts = line.strip().split()
            class_id = parts[0]
            x_center, y_center, w, h = map(float, parts[1:])
            boxes.append((class_id, x_center, y_center, w, h))
    return boxes

@tool
def crop_and_resize_images(image_dir: str,
    annotation_dir: str,
    output_dir: str)-> None:
    """
    Crops images into sliding windows, resizes the crops, and adjusts YOLO-format annotations accordingly.

    This tool processes a directory of images and their corresponding YOLO annotation files.
    Each image is converted to grayscale, and then cropped into fixed-size windows using a sliding window approach.
    Each crop is resized to a target size. For each crop, the function checks which bounding boxes from the original
    annotation overlap with the crop, clips them to the crop boundaries, and writes out new YOLO-format annotation files
    for the cropped images.

    Args:
        image_dir (str): Path to the directory containing input images.
        annotation_dir (str): Path to the directory containing YOLO-format annotation .txt files (one per image).
        output_dir (str): Path to the directory where cropped images and their annotations will be saved.
                          Two subdirectories, 'images' and 'labels', will be created inside this directory.

    Returns:
        None. The function saves cropped and resized images as PNG files and their corresponding YOLO annotation files
        in the specified output directory.

    Notes:
        - Only images with extensions .png, .jpg, or .jpeg are processed.
        - The function expects constants CROP_SIZE, STRIDE, RESIZE_SIZE, and START_ID to be defined in the global scope.
        - The function expects a helper function `parse_yolo_annotations(annotation_path)` to be defined,
          which parses a YOLO annotation file and returns a list of bounding boxes in the format:
          (class_id, x_center, y_center, width, height), where all values are normalized (0-1).
        - Each output crop will have its own annotation file, containing only the boxes that overlap with the crop,
          with coordinates adjusted and normalized to the crop window.
        - All output images are saved as grayscale PNGs.
        - Crops that do not contain any part of a bounding box are still saved, but their annotation files may be empty.

    Example:
        crop_and_resize_images(
            image_dir="data/images",
            annotation_dir="data/labels",
            output_dir="data/crops"
        )
    """
    images_dir = os.path.join(output_dir, "images")
    labels_dir = os.path.join(output_dir, "labels")
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(labels_dir, exist_ok=True)

    crop_id = START_ID

    for image_file in sorted(os.listdir(image_dir)):
        if not image_file.endswith((".png", ".jpg", ".jpeg")):
            continue

        image_path = os.path.join(image_dir, image_file)
        annotation_path = os.path.join(annotation_dir, os.path.splitext(image_file)[0] + ".txt")

        if not os.path.exists(annotation_path):
            continue

        image = cv2.imread(image_path)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        h, w = image.shape[:2]
        boxes = parse_yolo_annotations(annotation_path)
        print(f"Parsed {len(boxes)} boxes from {annotation_path}")


        for y in range(0, h - CROP_SIZE + 1, STRIDE):
            for x in range(0, w - CROP_SIZE + 1, STRIDE):
                crop_x2 = x + CROP_SIZE
                crop_y2 = y + CROP_SIZE

                crop = image[y:crop_y2, x:crop_x2]

                # Skip empty or invalid crops
                if crop is None or crop.shape[0] == 0 or crop.shape[1] == 0:
                    print(f"Skipping empty crop at x={x}, y={y}")
                    continue

                resized_crop = cv2.resize(crop, (RESIZE_SIZE, RESIZE_SIZE))

                crop_boxes = []
                for class_id, x_center, y_center, bw, bh in boxes:
                    box_left = x_center - bw / 2
                    box_right = x_center + bw / 2
                    box_top = y_center - bh / 2
                    box_bottom = y_center + bh / 2

                    if (box_left < crop_x2 and box_right > x and
                        box_bottom > y and box_top < crop_y2):

                        clipped_left = max(box_left, x)
                        clipped_right = min(box_right, crop_x2)
                        clipped_top = max(box_top, y)
                        clipped_bottom = min(box_bottom, crop_y2)

                        overlap_center_x = (clipped_left + clipped_right) / 2
                        overlap_center_y = (clipped_top + clipped_bottom) / 2
                        overlap_w = clipped_right - clipped_left
                        overlap_h = clipped_bottom - clipped_top

                        rel_x = (overlap_center_x - x) / CROP_SIZE
                        rel_y = (overlap_center_y - y) / CROP_SIZE
                        rel_w = overlap_w / CROP_SIZE
                        rel_h = overlap_h / CROP_SIZE


                        crop_boxes.append((class_id, rel_x, rel_y, rel_w, rel_h))

                crop_path = os.path.join(images_dir, f"{crop_id}.png")
                cv2.imwrite(crop_path, resized_crop)

                annotation_output_path = os.path.join(labels_dir, f"{crop_id}.txt")
                with open(annotation_output_path, "w") as f:
                    for class_id, rel_x, rel_y, rel_w, rel_h in crop_boxes:
                        f.write(f"{class_id} {rel_x:.7f} {rel_y:.7f} {rel_w:.7f} {rel_h:.7f}\n")

                crop_id += 1

def visualize_yolo(
    dataset_dir: str,
    dataset_name: str = "yolo-dataset",
    image_extension: str = ".png",
    classes: list[str] = ["symbol"],
    label_field: str = "symbols"
):
    """
    Loads a YOLO-formatted dataset into FiftyOne for visualization.

    This tool creates (or recreates) a FiftyOne dataset from a directory containing YOLO-format images and labels, 
    adds the images, attaches the YOLO labels, and launches the FiftyOne app for interactive exploration.

    Args:
        dataset_dir (str): Path to the root directory containing the YOLO dataset split (should contain 'train/images' and 'train/labels' subfolders).
        dataset_name (str, optional): Name for the FiftyOne dataset. Defaults to "yolo-dataset".
        image_extension (str, optional): File extension for the images (e.g., ".png", ".jpg"). Defaults to ".png".
        classes (list[str], optional): List of class names for the YOLO dataset. Defaults to ["symbol"].
        label_field (str, optional): The field name under which to store detections in FiftyOne. Defaults to "symbols".

    Returns:
        None. Launches the FiftyOne app for interactive visualization of the dataset.

    Notes:
        - If a dataset with the given name already exists, it will be deleted and recreated.
        - Assumes YOLO label files are in the 'train/labels' subdirectory and images in 'train/images'.
        - Requires FiftyOne and its YOLO utilities to be installed.
        - The function blocks until the FiftyOne app session is closed.

    Example:
        visualize_yolo(
            dataset_dir="data/SplitPreprocessedData",
            dataset_name="my-yolo-dataset",
            image_extension=".jpg",
            classes=["cat", "dog", "rabbit"],
            label_field="detections"
        )
    """
    dataset_name = "yolo-dataset"

    # Delete the dataset if it already exists
    if dataset_name in fo.list_datasets():
        fo.delete_dataset(dataset_name)
        print(f"Deleted existing dataset '{dataset_name}'.")

    # Create a new dataset
    dataset = fo.Dataset(name=dataset_name)
    print(f"Created new dataset '{dataset_name}'.")


    # Add samples (images) to the dataset
    dataset_dir = "data/SplitPreprocessedData"
    image_dir = f"{dataset_dir}/train/images"
    label_dir = f"{dataset_dir}/train/labels"

    image_paths = glob.glob(f"{image_dir}/*.png")  # Adjust extension if needed
    for img_path in image_paths:
        dataset.add_sample(fo.Sample(filepath=img_path))

    # model = foz.load_zoo_model("mobilenet-v2-imagenet-torch")
    # embeddings = dataset.compute_embeddings(model)

    # # Compute visualization
    # results = fob.compute_visualization(
    #     dataset, embeddings=embeddings, seed=51, brain_key="img_viz"
    # )


    fouy.add_yolo_labels(
        sample_collection=dataset,
        label_field="symbols",
        labels_path=label_dir,   # Directory containing YOLO .txt files
        classes=["symbol"],
        label_type="detections",
    )
    session = fo.launch_app(dataset)
    session.wait()
    

agent = CodeAgent(
    model=model,
    tools=[crop_and_resize_images],
    max_steps=10,
    additional_authorized_imports=["pandas", "numpy", "os"],
    verbosity_level=2
)
agent.logger.console.width=66
                
agent.run(
    """Can you preprocess the data from the relative folder data/Dataset_symbols and output it into data/AgentResult then visualize it in fiftyone"""
)