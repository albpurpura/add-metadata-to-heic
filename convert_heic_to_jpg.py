import os
import argparse
from pyheif import read
from PIL import Image
from tqdm import tqdm
import json
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import datetime
import piexif
from geopy.geocoders import Nominatim
import re

geolocator = Nominatim(user_agent="geo_location_app")

def sanitize_filename(filename):
    # Define a regex pattern to match characters not allowed in filenames
    invalid_chars = r'[\\/:"*?<>|]'

    # Replace invalid characters with underscores
    sanitized_filename = re.sub(invalid_chars, '_', filename)

    return sanitized_filename


def compute_photo_dest_dir(main_dir, metadata, use_location=True):
    # Initialize a geolocator using Nominatim

    if use_location and "geoData" in metadata:
        latitude = metadata["geoData"]["latitude"]
        longitude = metadata["geoData"]["longitude"]
        # Perform reverse geocoding to get the location name
        location = geolocator.reverse((latitude, longitude), exactly_one=True)
        # Extract the location name
        # Extract the city or area name
        city = location.raw.get('address', {}).get('city', '')
        area = location.raw.get('address', {}).get('county', '')

        # If city is not available, use area
        location_name = sanitize_filename(city) if city else sanitize_filename(area)
        # location_name = sanitize_filename(location.address) if location else "UNK"
    else:
        location_name = False
        location_name = "UNK"

    timestamp = int(metadata["photoTakenTime"]["timestamp"])
    formatted_time = datetime.datetime.fromtimestamp(timestamp)
    year = formatted_time.year
    month = formatted_time.month
    if location_name:
        fpath = os.path.join(os.path.join(os.path.join(main_dir, location_name), str(year)), str(month))
    else:
        fpath = os.path.join(os.path.join(main_dir, str(year)), str(month))
    return fpath


def add_exif_data(image_path, user_data):
    try:
        image = Image.open(image_path)
        exif_bytes = image.info.get("exif", b"")
        exif_dict = (
            piexif.load(exif_bytes)
            if exif_bytes
            else {"0th": {}, "Exif": {}, "GPS": {}, "ImageIFD": {}}
        )

        exif_dict["Exif"][piexif.ExifIFD.UserComment] = json.dumps(user_data).encode(
            "utf-8"
        )

        for key, value in user_data.items():
            # Convert formatted timestamp to datetime object
            if key == "photoTakenTime":
                timestamp = int(value["timestamp"])
                formatted_time = datetime.datetime.fromtimestamp(timestamp)
                exif_dict["Exif"][36867] = formatted_time.strftime("%Y:%m:%d %H:%M:%S")
            # Map other keys to EXIF tags
            elif key == "people":
                people = ", ".join([p["name"] for p in value])
                exif_dict["ImageIFD"][piexif.ImageIFD.XPKeywords] = people
            elif key in piexif.TAGS["Exif"]:
                exif_dict["Exif"][piexif.TAGS["Exif"][key]] = str(value).encode("utf-8")

        if "geoData" in user_data:
            latitude = user_data["geoData"]["latitude"]
            longitude = user_data["geoData"]["longitude"]

            # Convert latitude and longitude to rational format
            gps_latitude = (
                int(abs(latitude) * 1000000),  # Degrees * 1e6
                1000000,
            )

            gps_longitude = (
                int(abs(longitude) * 1000000),  # Degrees * 1e6
                1000000,
            )

            exif_dict["GPS"] = {
                piexif.GPSIFD.GPSLatitudeRef: "N" if latitude >= 0 else "S",
                piexif.GPSIFD.GPSLongitudeRef: "E" if longitude >= 0 else "W",
                piexif.GPSIFD.GPSLatitude: gps_latitude,
                piexif.GPSIFD.GPSLongitude: gps_longitude,
            }

        exif_bytes = piexif.dump(exif_dict)

        # Save the image with updated EXIF data
        image.save(image_path, "jpeg", exif=exif_bytes)
        # print("EXIF data added successfully.")

    except Exception as e:
        print(f"An error occurred: {e}")


def convert_img(heic_path, jpg_path):
    heif_file = read(heic_path)
    image = Image.frombytes(
        heif_file.mode,
        heif_file.size,
        heif_file.data,
        "raw",
        heif_file.mode,
        heif_file.stride,
    )
    image.save(jpg_path, "JPEG")


def add_metadata_to_jpg_file(jpg_fpath, img_metadata_fpath):
    with open(img_metadata_fpath) as f:
        metadata = json.load(f)
        add_exif_data(jpg_fpath, metadata)


def convert_heic_to_jpg(source_dir, destination_dir):
    # Create the destination directory if it doesn't exist
    os.makedirs(destination_dir, exist_ok=True)

    # Iterate through the files and subdirectories in the source directory
    for root, _, files in os.walk(source_dir):
        for filename in tqdm(files):
            if filename.endswith(".HEIC"):
                heic_path = os.path.join(root, filename)
                relative_path = os.path.relpath(heic_path, source_dir)

                try:
                    img_metadata_fpath = heic_path + ".json"
                    if os.path.exists(img_metadata_fpath):
                        metadata = json.load(open(img_metadata_fpath))
                        target_dir = compute_photo_dest_dir(
                            destination_dir, metadata, use_location=True
                        )
                        jpg_path = os.path.join(target_dir, os.path.splitext(relative_path)[0] + ".jpg")
                    else:
                        jpg_path = os.path.join(
                            destination_dir, os.path.splitext(relative_path)[0] + ".jpg"
                        )
                    os.makedirs(os.path.dirname(jpg_path), exist_ok=True)
                    convert_img(heic_path, jpg_path)
                    add_metadata_to_jpg_file(jpg_path, img_metadata_fpath)
                    assert os.path.exists(jpg_path)

                except Exception as e:
                    print(f"Error converting file: {heic_path} ({e})")


def main():
    parser = argparse.ArgumentParser(description="Convert HEIC files to JPG")
    parser.add_argument(
        "--source_dir",
        help="Source directory containing HEIC files",
        required=True,
        default="./photos_orig",
    )
    parser.add_argument(
        "--destination_dir",
        help="Destination directory for JPG files",
        required=True,
        default="./jpg_photos",
    )

    args = parser.parse_args()

    source_dir = args.source_dir
    destination_dir = args.destination_dir

    convert_heic_to_jpg(source_dir, destination_dir)
    print("Conversion complete.")


if __name__ == "__main__":
    main()
