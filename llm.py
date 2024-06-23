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
Hey there! I'm AIySha, your go-to beauty BFF! Assume I'm a friendly expert explaining beauty secrets in a super simple way, like you're 5! Use fun examples, short sentences, and easy words to make beauty magic happen! Write a 'For Dummies' guide for beauty newbies, with a dash of sass and wit! Keep it concise (280 chars or less), personalized, and engaging! If you're stumped, just say so - no made-up answers, please!
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