from google.cloud import aiplatform
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)

PROJECT = os.getenv("PROJECT")
ENDPOINT_ID = os.getenv("ENDPOINT_ID")
LOCATION = os.getenv("LOCATION")
API_ENDPOINT = os.getenv("API_ENDPOINT")

SYSTEM_PROMPT = """<s>[INST]
<<SYS>>
I want you to act as a makeup artist named Aiysha. You will apply cosmetics on clients in order to enhance features, create looks and styles according to the latest trends in beauty and fashion, offer advice about skincare routines, know how to work with different textures of skin tone, and be able to use both traditional methods and new techniques for applying products. You will always respond in 280 characters or less. My first suggestion request is: 
<</SYS>>
"""

def get_llama_response(input_data):
    client_options = {"api_endpoint": API_ENDPOINT}
    client = aiplatform.gapic.PredictionServiceClient(client_options=client_options)
    endpoint = client.endpoint_path(
        project=PROJECT, location=LOCATION, endpoint=ENDPOINT_ID
    )
    instances = [
        {"inputs": input_data, 
         "parameters": {"max_tokens": 60}
        }
    ]
    response = client.predict(endpoint=endpoint, instances=instances)
    return response.predictions

def format_llama_prompt(message: str) -> str:
    formatted_prompt = SYSTEM_PROMPT + f"{message} [/INST]"
    return formatted_prompt

def get_model_response(message: str):
    query = format_llama_prompt(message)

    generated_text = get_llama_response(query)
       
    if generated_text:
         response_text = generated_text[0]
         response_start = response_text.find('Output:') + len('Output:')
         response = response_text[response_start:].strip()
    else:
         response = ""

    return response