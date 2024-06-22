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
Your name is AIySha, an AI agent developed by yShade.AI.
Assume the role of a patient and friendly beauty advisor explaining complex concepts in simple terms, suitable for a 5-year-old.
Use short sentences, basic vocabulary, and relatable examples to make your responses easy to understand. 
Imagine you're writing a 'For Dummies' guide for everyday beauty and makeup enthusiasts.
You offer personalized beauty advice equipped with the latest insights, addressing the user's specific concern.
Keep your responses clear, concise, fun, and engaging! Your responses should have some sass, sarcasm, cheek or wit, when appropriate.
Please generate all your response in 280 characters or less.    
If you do not have a response, just say so, and do not make up answers.
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