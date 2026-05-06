import os

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobClient
from dotenv import load_dotenv
from pathlib import Path

# MUST BE FIRST! Retrieve the storage blob service URL, which is of the form
# https://<your-storage-account-name>.blob.core.windows.net/
load_dotenv(Path(__file__).resolve().parent / ".env")
storage_url = os.environ["AZURE_STORAGE_BLOB_URL"]

credential = DefaultAzureCredential()

# Set up the connection string and container name
container_name = "csvcache"
blob_name = "dividend_history.csv"
local_file_name = Path(__file__).resolve().parent / "cache" / "dividend_history.csv"

# Create the client object using the storage URL and the credential
blob_client = BlobClient(
    storage_url,
    container_name=container_name,
    blob_name=blob_name,
    credential=credential)

# blob_client.download_blob(local_file_name)

# Upload a CSV file to the blob container
with open(local_file_name, "rb") as data:
    blob_client.upload_blob(data)

# Download the blob and print its contents
downloaded_blob = blob_client.download_blob().readall()
print(downloaded_blob.decode("utf-8"))
