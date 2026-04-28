import pyseekdb


def get_collection(
    collection_name: str = None, host: str = "127.0.0.1", port: int = 2881
):
    client = pyseekdb.Client(
        host=host,  # server host
        port=port,  # server port (default: 2881)
    )

    # create a knowledge base
    collection = client.get_or_create_collection(collection_name)
    return collection
