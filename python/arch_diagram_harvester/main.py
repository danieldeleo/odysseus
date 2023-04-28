import base64
import io, re
from typing import List, Sequence, Union
from collections import Counter, defaultdict
import urllib.parse

from google.cloud import aiplatform, storage, vision, firestore
from google.cloud.aiplatform.gapic.schema import predict
import json

# The AI Platform services require regional API endpoints.
api_endpoint = "us-central1-aiplatform.googleapis.com"
client_options = {"api_endpoint": api_endpoint}
aiplatform_client = aiplatform.gapic.PredictionServiceClient(
    client_options=client_options
)
storage_client = storage.Client()
vision_client = vision.ImageAnnotatorClient()
firestore_client = firestore.Client()


def list_blob_names(bucket_name, prefix):
    """Lists all the blobs in the bucket that begin with the prefix.

    This can be used to list all blobs in a "folder", e.g. "public/".
    """
    blobs_iter = storage_client.list_blobs(bucket_name, prefix=prefix)
    blobs = []
    for blob in blobs_iter:
        blobs.append(blob.name)
    return blobs


def upload_blob_from_stream(bucket_name, file_obj, destination_blob_name):
    """Uploads bytes from a stream or other file-like object to a blob."""
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    file_obj.seek(0)
    blob.upload_from_file(file_obj)
    print(f"Stream data uploaded to {destination_blob_name} in bucket {bucket_name}.")


def create_jsonl_dataset_file(bucket_name, destination_blob_name):
    images = list_blob_names(bucket_name, "images_since_2020/")
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    with io.BytesIO() as f:
        for image in images:
            f.write(
                bytes(
                    '{"imageGcsUri": "gs://' + bucket_name + "/" + image + '"}\n',
                    "utf-8",
                )
            )
        f.seek(0)
        blob.upload_from_file(f)


def create_jsonl_batch_prediction_file(bucket_name, destination_blob_name):
    images = list_blob_names(bucket_name, "images_since_2020/")
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    with io.BytesIO() as f:
        for image in images:
            f.write(
                bytes(
                    '{"content": "gs://'
                    + bucket_name
                    + "/"
                    + image
                    + '", "mimeType": "image/jpeg"}\n',
                    "utf-8",
                )
            )
        f.seek(0)
        blob.upload_from_file(f)


def download_blob_to_stream(bucket_name, source_blob_name):
    """Downloads a blob to a stream or other file-like object."""
    file_obj = io.BytesIO()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(source_blob_name)
    blob.download_to_file(file_obj)
    file_obj.seek(0)
    return file_obj.read()


def copy_diagrams_to_folder(bucket_name, diagrams_prefix, destination_prefix):
    blobs_iter = storage_client.list_blobs(bucket_name, prefix=diagrams_prefix)
    bucket = storage_client.bucket(bucket_name)
    for blob in blobs_iter:
        file_obj = io.BytesIO()
        print(blob.name)
        bucket.blob(blob.name).download_to_file(file_obj)
        file_obj.seek(0)
        for line in file_obj:
            json_prediction = json.loads(line)
            image_uri = json_prediction.get("instance").get("content")
            display_name = json_prediction.get("prediction").get("displayNames")[0]
            arch_diagram_confidence_index = 0 if display_name == "arch_diagram" else 1
            arch_diagram_confidence = json_prediction.get("prediction").get(
                "confidences"
            )[arch_diagram_confidence_index]
            # print(f"image_uri: {image_uri} confidence: {arch_diagram_confidence}")
            source_blob = bucket.blob(
                image_uri.replace("gs://" + bucket_name + "/", "")
            )
            # print(f"destination: {bucket_name}/{destination_prefix}/{source_blob.name}")
            if arch_diagram_confidence == 1:
                blob_copy = bucket.copy_blob(
                    source_blob, bucket, f"{destination_prefix}/{source_blob.name}"
                )


def get_image_text_for_bucket_images(bucket_name, prefix):
    blobs_iter = storage_client.list_blobs(bucket_name, prefix=prefix)
    word_to_images = defaultdict(list)
    for blob in blobs_iter:
        word_to_images_doc_ref = firestore_client.collection("image_text").document("word_to_images")
        image_to_words_doc_ref = firestore_client.collection("image_text").document("image_to_words")
        word_to_images = defaultdict(list, word_to_images_doc_ref.get().to_dict() or {})
        image_to_words = image_to_words_doc_ref.get().to_dict() or {}
        detect_text_uri(f"gs://{bucket_name}/{blob.name}", word_to_images, image_to_words)
        print(word_to_images)
        try:
            word_to_images_doc_ref.set(word_to_images)
            image_to_words_doc_ref.set(image_to_words)
        except Exception as e:
            print(e)


def detect_text_uri(uri, image_text, image_to_words):
    """Detects text in the file located in Google Cloud Storage or on the Web."""

    image = vision.Image()
    image.source.image_uri = uri
    url = f"https://storage.cloud.google.com/{urllib.parse.quote_plus(uri.split('gs://')[1])}"

    response = vision_client.text_detection(image=image)
    texts = response.text_annotations
    unique_words = set()
    for text in texts:
        text.description = text.description.replace("\n", " ")
        for word in text.description.split(" "):
            word = word.strip("-").strip("_").lower()
            if is_word(word):
                unique_words.add(word)
    for word in unique_words:
        image_text[word].append(url)
    image_to_words[url] = list(unique_words)


def is_word(text):
    return re.match(r"^[a-zA-Z_\-]*$", text) and len(text) > 1


def predict_image_classification_sample(
    project: str, endpoint_id: str, filename: str, location: str = "us-central1"
):
    file_content = download_blob_to_stream("psotddimages", filename)
    encoded_content = base64.b64encode(file_content).decode("utf-8")
    instance = predict.instance.ImageClassificationPredictionInstance(
        content=encoded_content,
    ).to_value()
    instances = [instance]
    parameters = predict.params.ImageClassificationPredictionParams(
        confidence_threshold=0.5,
        max_predictions=5,
    ).to_value()
    endpoint = aiplatform_client.endpoint_path(
        project=project, location=location, endpoint=endpoint_id
    )
    response = aiplatform_client.predict(
        endpoint=endpoint, instances=instances, parameters=parameters
    )
    print("response")
    print(" deployed_model_id:", response.deployed_model_id)
    predictions = response.predictions
    for prediction in predictions:
        print(" prediction:", dict(prediction))


def create_and_import_dataset_image_sample(
    project: str,
    location: str,
    display_name: str,
    src_uris: Union[str, List[str]],
    sync: bool = True,
):
    """
    src_uris -- a string or list of strings, e.g.
        ["gs://bucket1/source1.jsonl", "gs://bucket7/source4.jsonl"]
    """

    aiplatform.init(project=project, location=location)

    ds = aiplatform.ImageDataset.create(
        display_name=display_name,
        gcs_source=src_uris,
        import_schema_uri=aiplatform.schema.dataset.ioformat.image.single_label_classification,
        sync=sync,
    )

    ds.wait()

    print(ds.display_name)
    print(ds.resource_name)
    return ds


def create_batch_prediction_job_sample(
    project: str,
    location: str,
    model_resource_name: str,
    job_display_name: str,
    gcs_source: Union[str, Sequence[str]],
    gcs_destination: str,
    sync: bool = True,
):
    aiplatform.init(project=project, location=location)

    my_model = aiplatform.Model(model_resource_name)

    batch_prediction_job = my_model.batch_predict(
        job_display_name=job_display_name,
        gcs_source=gcs_source,
        gcs_destination_prefix=gcs_destination,
        sync=sync,
    )

    batch_prediction_job.wait()

    print(batch_prediction_job.display_name)
    print(batch_prediction_job.resource_name)
    print(batch_prediction_job.state)
    return batch_prediction_job


def get_top_n_words_from_diagrams(top_n):
    doc_ref = firestore_client.collection("image_text").document("word_to_images")
    image_text = doc_ref.get().to_dict() or {}
    c = Counter(image_text)
    top_common = c.most_common(top_n)
    for t in top_common:
        if len(t[0]) > 2:
            print(f"{t[0]} : {t[1]}")
    print(f"Total Words: {len(c)}")


def main():
    # create_jsonl_dataset_file("psotddimages", "image_list.jsonl")
    # create_and_import_dataset_image_sample(
    #     project="125344609093",
    #     location="us-central1",
    #     display_name="2020_to_2023_images",
    #     src_uris="gs://psotddimages/image_list.jsonl",
    # )
    # create_jsonl_batch_prediction_file("psostarterkituscentral1", "batch_predict.jsonl")
    # create_batch_prediction_job_sample(
    #     project="125344609093",
    #     location="us-central1",
    #     model_resource_name="2252795971220013056",
    #     job_display_name="hellworld",
    #     # {"content": "gs://sourcebucket/datasets/images/source_image.jpg", "mimeType": "image/jpeg"}
    #     gcs_source="gs://psotddimages/batch_predict_input.jsonl",
    #     gcs_destination="gs://psotddimages/batch_predict_output",
    # )
    # predict_image_classification_sample(
    #     project="125344609093",
    #     endpoint_id="6485372579413491712",
    #     location="us-central1",
    #     filename="images_since_2020/1-FLoCXJzENvQMV7eEEyzISpPuSuYBirwFu3SxTsDuKg∕image12.png"
    # )
    # copy_diagrams_to_folder(
    #     "psostarterkituscentral1",
    #     "2020_to_2023_images_predictions/",
    #     "2020_to_2023_diagrams",
    # )
    get_image_text_for_bucket_images(
        "psostarterkituscentral1", "2020_to_2023_diagrams/images_since_2020/"
    )
    # get_top_n_words_from_diagrams(100)
    
    # doc_ref = firestore_client.collection("image_text").document("word_to_images")
    # image_text = doc_ref.get().to_dict() or {}
    # count_map = defaultdict(list)
    # for word in image_text:
    #     if len(word) > 1:
    #         count_map[image_text[word]].append(word)
    # for count in sorted(count_map.keys(), reverse=True):
    #     print(f"{count} : {count_map[count]}")


if __name__ == "__main__":
    main()
