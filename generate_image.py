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
from PIL import Image
from io import BytesIO

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


async def make_character(prompt_text: str, workflow: dict, image, emotion: str):
    print(f"Starting image generation for {emotion}")
    
    random_seed = random.randint(0, 2**32 - 1)
    workflow["25"]["inputs"]["text"] = prompt_text
    workflow["34"]["inputs"]["text"] = prompt_text
    workflow["19"]["inputs"]["noise_seed"] = random_seed
    workflow["28"]["inputs"]["noise_seed"] = random_seed

    url = f"{COMFYUI_URL}/upload/image"
    unique_filename = f"{uuid.uuid4()}.png"
    form = aiohttp.FormData()

    # 이미지 타입에 따른 처리
    if isinstance(image, UploadFile):
        file_content = await image.read()
        await image.seek(0)
        content_type = image.content_type
    else:  # PIL Image
        img_byte_arr = BytesIO()
        image.save(img_byte_arr, format='PNG')
        file_content = img_byte_arr.getvalue()
        content_type = "image/png"

    form.add_field("image", file_content, filename=unique_filename, content_type=content_type)
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
    
async def generate_image_websocket(uid: str, image_data : bytes):
    print("generate_image_websocket 호출")
    print(uid)
    print(image_data)
    print("===============================")   
    try:
        workflow = await load_workflow('workflow.json')
        
        emotions = ["joy", "sadness", "anger", "disgust", "serious"]
        emotion_images = {}

        for emotion in emotions:
            try:
                result = await make_character_websocket(prompt[emotion], copy.deepcopy(workflow), image_data, emotion)
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

async def make_character_websocket(prompt_text: str, workflow: dict, image: Image.Image, emotion: str):
    print(f"Starting image generation for {emotion}")
    
    # PIL 이미지 객체를 바이트로 변환
    img_byte_arr = BytesIO()
    image.save(img_byte_arr, format='PNG')
    image_data = img_byte_arr.getvalue()
    
    # 랜덤 시드 생성
    random_seed = random.randint(0, 2**32 - 1)
    
    # 25,34 positive prompt
    workflow["25"]["inputs"]["text"] = prompt_text
    workflow["34"]["inputs"]["text"] = prompt_text

    # 7,24 negative prompt (기존과 동일)
    workflow["7"]["inputs"]["text"] = "cross-eyed, unnatural eye alignment, distorted gaze direction, mismatched eye position, asymmetrical eyes, exaggerated reflections in eyes, blurred lips, smudged lips, distorted mouth, missing teeth, uneven teeth, broken teeth, overly sharp or exaggerated teeth, unnatural skin texture, unrealistic facial symmetry, artifacts, low quality, deformed face features, blurry details"
    workflow["24"]["inputs"]["text"] = "cross-eyed, unnatural eye alignment, distorted gaze direction, mismatched eye position, asymmetrical eyes, exaggerated reflections in eyes, blurred lips, smudged lips, distorted mouth, missing teeth, uneven teeth, broken teeth, overly sharp or exaggerated teeth, unnatural skin texture, unrealistic facial symmetry, artifacts, low quality, deformed face features, blurry details"

    # 랜덤 시드 적용 (19번과 28번 노드에 동일한 시드 적용)
    workflow["19"]["inputs"]["noise_seed"] = random_seed
    workflow["28"]["inputs"]["noise_seed"] = random_seed

    url = f"{COMFYUI_URL}/upload/image"

    # 고유한 파일 이름 생성
    unique_filename = f"{uuid.uuid4()}.png"

    form = aiohttp.FormData()
    form.add_field("image", image_data, filename=unique_filename, content_type="image/png")
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



async def generate_v2_persona_image(uid, final_image, customPersona, prompt, db):
    print("generate_v2_persona_image 호출")
    print(uid)
    print(final_image)
    print(customPersona)
    print(prompt)

    try:
        workflow = await load_workflow('workflow.json')
        
        # emotions = ["joy", "sadness", "anger", "custom", "clone"]
        emotions = ["custom", "clone" , "joy" , "anger" , "sadness"]
        emotion_images = {}

        user_ref = db.collection('users').document(uid)

        

        user_doc = user_ref.get().to_dict()

        print("=================================")

        user_persona = user_doc['persona']
        
        print(user_persona)
        for emotion in emotions:
            try:
                result = await make_character(prompt[emotion], copy.deepcopy(workflow), final_image, emotion)
                emotion_images[emotion] = result
                print(f"Generated image for {emotion}: {result}")

            except Exception as e:
                print(f"Error generating image for {emotion}: {str(e)}")
                emotion_images[emotion] = {'status': 'error', 'message': str(e)}
            
            # 각 요청 사이에 잠시 대기
            await asyncio.sleep(2)
        


        print('9999')


        while len(user_persona) < 5:
            index = len(user_persona)
            user_persona.append({})


        # print(1)
        # user_persona[0]['IMG'] = emotion_images['custom']['image_url']
        # print(2)
        # user_persona[1]['IMG'] = emotion_images['clone']['image_url']
        # print(3)
        # user_persona[2]['Name'] = "Joy"
        # user_persona[2]['IMG'] = emotion_images['joy']['image_url']
        # print(4)
        # user_persona[3]['Name'] = "Anger"
        # user_persona[3]['IMG'] = emotion_images['anger']['image_url']
        # print(5)
        # user_persona[4]['Name'] = "Sadness"
        # user_persona[4]['IMG'] = emotion_images['sadness']['image_url']


        for i, persona in enumerate(user_persona):
            if i == 0:
                persona['IMG'] = emotion_images['custom']['image_url']
            elif i == 1:
                persona['IMG'] = emotion_images['clone']['image_url']
            elif i == 2:
                persona['IMG'] = emotion_images['joy']['image_url']
                persona['Name'] = 'Joy'  # 필요한 경우 이름 수정
                persona['DPNAME'] = "기쁨이"
            elif i == 3:
                persona['IMG'] = emotion_images['anger']['image_url']
                persona['Name'] = 'Anger'
                persona['DPNAME'] = '화남이'
            elif i == 4:
                persona['IMG'] = emotion_images['sadness']['image_url']
                persona['Name'] = 'Sadness'
                persona['DPNAME'] = "슬픔이"

            
        print("Updated user_persona:", user_persona)

        print('1111')

        user_ref.set(
            {"persona" : user_persona},
            merge=True
        )

        print('1212')

        return {"status": "complete", "images": emotion_images}
    except Exception as e:
        print(f"Error in generate_persona_image: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")



    



