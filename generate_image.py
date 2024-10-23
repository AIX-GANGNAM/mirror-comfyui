from image_prompt import prompt
import json
import os
import aiohttp
import uuid
from firebase_admin import storage
from fastapi import HTTPException, File, UploadFile
import asyncio
import copy
import random

COMFUI_OUTPUT_DIR = r"C:\Users\201-29\Downloads\StabilityMatrix-win-x64\Data\Packages\ComfyUI\output"
COMFYUI_URL = "http://127.0.0.1:8188"

async def load_workflow(workflow_path):
    try:
        with open(workflow_path, 'r', encoding='utf-8') as file:
            workflow = json.load(file)
            return workflow
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Workflow not found")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid workflow format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

async def generate_persona_image(uid: str, image: UploadFile = File(...)):
    print("Persona image generation service started")

    try:
        workflow = await load_workflow('workflow.json')
        
        emotions = ["joy", "sadness", "anger", "disgust", "serious"]
        emotion_images = {}

        for emotion in emotions:
            try:
                result = await make_character(prompt[emotion], copy.deepcopy(workflow), image, emotion)
                emotion_images[emotion] = result
                print(f"Generated image for {emotion}: {result}")
            except Exception as e:
                print(f"Error generating image for {emotion}: {str(e)}")
                emotion_images[emotion] = {'status': 'error', 'message': str(e)}
            
            # 각 요청 사이에 잠시 대기
            await asyncio.sleep(2)
        
        return {"status": "complete", "images": emotion_images}
    except Exception as e:
        print(f"Error in generate_persona_image: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

async def queue_prompt(workflow: dict, client_id: str = ""):
    print("queue_prompt 서비스 실행")
    prompt_url = f"{COMFYUI_URL}/prompt"

    payload = {
        "prompt": workflow,
        "client_id": client_id
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(prompt_url, json=payload) as response:
            if response.status != 200:
                raise HTTPException(status_code=response.status, detail=f"Error queueing prompt: {await response.text()}")
            result = await response.json()
            return result.get("prompt_id")
    
async def check_progress(prompt_id: str):
    print(f"Checking progress for prompt_id: {prompt_id}")
    history_url = f"{COMFYUI_URL}/history/{prompt_id}"
    max_retries = 60  # 최대 60번 시도 (1분)
    retry_count = 0
    async with aiohttp.ClientSession() as session:
        while retry_count < max_retries:
            print(f"Retry count: {retry_count}")
            async with session.get(history_url) as response:
                if response.status == 200:
                    history = await response.json()
                    if prompt_id in history:
                        return history[prompt_id]
            await asyncio.sleep(1)  # 1초 대기
            retry_count += 1
    print(f"Max retries reached for prompt_id: {prompt_id}")
    return None  # 최대 시도 횟수를 초과하면 None 반환


def upload_image_to_firebase(local_image_path, destination_blob_name):
    bucket = storage.bucket()
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_filename(local_image_path)

    blob.make_public()
    return blob.public_url


async def make_character(prompt_text: str, workflow: dict, image: UploadFile, emotion: str):
    print(f"Starting image generation for {emotion}")
    
    # 랜덤 시드 생성
    random_seed = random.randint(0, 2**32 - 1)
    
    # 25,34 positive prompt
    workflow["25"]["inputs"]["text"] = prompt_text
    workflow["34"]["inputs"]["text"] = prompt_text

    # 7,24 negative prompt (기존과 동일)
    workflow["7"]["inputs"]["text"] = "Avoid cross-eyed appearances, unnatural eye alignment, or any distortion in the direction of the gaze. Ensure that the eyes are naturally aligned and symmetrical, with pupils centered and looking in the same direction. Do not generate mismatched or asymmetrical eye positions, and avoid any overly exaggerated or distorted reflections in the eyes`"
    workflow["24"]["inputs"]["text"] = "Avoid cross-eyed appearances, unnatural eye alignment, or any distortion in the direction of the gaze. Ensure that the eyes are naturally aligned and symmetrical, with pupils centered and looking in the same direction. Do not generate mismatched or asymmetrical eye positions, and avoid any overly exaggerated or distorted reflections in the eyes"

    # 랜덤 시드 적용 (19번과 28번 노드에 동일한 시드 적용)
    workflow["19"]["inputs"]["noise_seed"] = random_seed
    workflow["28"]["inputs"]["noise_seed"] = random_seed

    url = f"{COMFYUI_URL}/upload/image"
    file_content = await image.read()
    await image.seek(0)  # 파일 포인터를 처음으로 되돌림

    # 파일 확장자 추출
    _, ext = os.path.splitext(image.filename)
    # 고유한 파일 이름 생성
    unique_filename = f"{uuid.uuid4()}{ext}"

    form = aiohttp.FormData()
    form.add_field("image", file_content, filename=unique_filename, content_type=image.content_type)
    form.add_field('overwrite', 'true')

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=form) as response:
            if response.status == 200:
                workflow["1"]['inputs']['image'] = unique_filename
                prompt_id = await queue_prompt(workflow)
                result = await check_progress(prompt_id)

                if result is None:
                    return {'status': 'error', 'message': f'Timeout while generating image for {emotion}'}

                if 'outputs' in result and '39' in result['outputs']:
                    final_image_url = result['outputs']['39']['images'][0]['filename']
                else:
                    print(f"Unexpected result structure for {emotion}: {result}")
                    return {'status': 'error', 'message': f'Unexpected result structure for {emotion}'}

    if final_image_url:
        local_image_path = os.path.join(COMFUI_OUTPUT_DIR, final_image_url)
        destination_blob_name = f"generate_images/{emotion}_{final_image_url}"
        firebase_url = upload_image_to_firebase(local_image_path, destination_blob_name)
        return {'status': 'complete', 'image_url': firebase_url}
    else:
        return {'status': 'error', 'message': f'Failed to generate image for {emotion}'}
        
async def regenerate_image(emotion: str, image: UploadFile = File(...)):
    print(f"Regenerating image for {emotion}")

    try:
        workflow = await load_workflow('workflow.json')

        result = await make_character(prompt[emotion], copy.deepcopy(workflow), image, emotion)
        return result
    except Exception as e:
        print(f"Error in regenerate_image: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")