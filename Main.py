from fastapi import FastAPI, File, UploadFile, WebSocket
from PIL import Image
import json
import base64
import io
import os
from firebase_admin import firestore
import firebase_admin
from firebase_admin import credentials

from generate_image import *
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()



app = FastAPI()

app.add_middleware(
       CORSMiddleware,
       allow_origins=["*"],  # 실제 운영 환경에서는 구체적인 origin을 지정하세요
       allow_credentials=True,
       allow_methods=["*"],
       allow_headers=["*"],
   )

@app.post("/generate-persona-image/{uid}")
async def generate_persona_image_endpoint(uid: str, image : UploadFile=File(...)):
    return await generate_persona_image(uid,image)

@app.post("/regenerate-image/{emotion}")
async def regenerate_image_endpoint(emotion: str, image : UploadFile=File(...)):
    return await regenerate_image(emotion, image)

@app.websocket("/image-generate-default/{uid}/{gender}")
async def image_generate_default(uid: str, gender: str, websocket: WebSocket):
    await websocket.accept()
    
    try:
        # 클라이언트로부터 이미지 데이터 수신
        data = await websocket.receive_text()
        image_data = json.loads(data)
        
        if 'image' in image_data and image_data['image']:
            print(1)
            # 사용자가 이미지를 보냈을 경우
            image_bytes = base64.b64decode(image_data['image'])
            image = Image.open(io.BytesIO(image_bytes))
        else:
            print(2)
            # 사용자가 이미지를 보내지 않았을 경우
            default_image = 'female.webp' if gender.lower() == 'female' else 'male.webp'
            image_path = os.path.join('asset/persona/', default_image)
            print(3)
            image = Image.open(image_path)
        
        # 이미지 처리 또는 저장
        response = await generate_persona_image(uid, image)
        print(4)

        print("response : ", response['images'])

        db = firestore.client()
        print(5)
        doc_ref = db.collection('users').document(uid).collection('persona')
        print(6)

        if response['status'] == 'complete':
            images = response['images']
            persona_data = {
                'anger' : images['anger'],
                'disgust' : images['disgust'],
                'joy' : images['joy'],
                'sadness' : images['sadness'],
                'serious' : images['serious']
            }
            doc_ref.set(persona_data)
            
            # 클라이언트에 성공 응답
            await websocket.send_text(json.dumps({
                "status": "success",
                "message": "페르소나 이미지가 생성되고 저장되었습니다.",
                "images": persona_data
            }))
        else:
            # 이미지 생성 실패 시
            await websocket.send_text(json.dumps({
                "status": "error",
                "message": "페르소나 이미지 생성에 실패했습니다."
            }))
        
    except Exception as e:
        print(f"오류 발생: {str(e)}")
        await websocket.send_text(json.dumps({"status": "error", "message": str(e)}))
    
    finally:
        await websocket.close()

def generate_image(gender: str) -> Image.Image:
    # 실제 이미지 생성 로직을 여기에 구현
    # 이 예제에서는 간단히 빈 이미지를 생성합니다
    return Image.new('RGB', (100, 100), color = 'red')

@app.get("/networkcheck")
async def network_check_endpoint():
    print("network_check_endpoint 호출")
    return {"message": "Network check successful"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        try:
            data = await websocket.receive_text()
            await websocket.send_text(f"서버에서 받은 메시지: {data}")
        except Exception as e:
            print(f"오류 발생: {str(e)}")
            break


if __name__ == "__main__":
    import uvicorn
    print("FastAPI 서버 실행")
    uvicorn.run(app, host="0.0.0.0", port=1818)