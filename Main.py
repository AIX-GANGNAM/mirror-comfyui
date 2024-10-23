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

cred = credentials.Certificate("mirrorgram-20713-firebase-adminsdk-u9pdx-c3e12134b4.json")
firebase_admin.initialize_app(cred, {
    'storageBucket': 'mirrorgram-20713.appspot.com'
})



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

@app.post("/image-generate-default/{uid}/{gender}")
async def image_generate_default(uid: str, gender: str , image : UploadFile=File(...)):
    print("image_generate_default 호출")
    print(gender)
    print(image)
    if image is None:
        if gender == "male":
            image_path = 'assets/images/male.jpg'
        else:
            image_path = 'assets/images/female.webp'
        
        image = load_image(image_path)
        
        if image is None:
            print("기본 이미지를 불러오는 데 실패했습니다.")
            # 여기에 오류 처리 로직을 추가할 수 있습니다.
            return await generate_persona_image(uid,image)
        else:
            return await generate_persona_image(uid,image)
    else:
        return await generate_persona_image(uid,image)
    



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

@app.websocket("/image-generate-default/{uid}")
async def image_generate_default_websocket(uid: str, websocket: WebSocket):
    print("image_generate_default_websocket 호출")
    print(uid)
    print(websocket)
    
    print("===============================")
    await websocket.accept()
    gender = None
    
    try:
        # 클라이언트로부터 이미지 데이터 수신
        data = await websocket.receive_text()
        image_data = json.loads(data)
        print("성별")
        print(image_data['gender'])
        
        if 'image' in image_data and image_data['image']:
            print(1)
            # 사용자가 이미지를 보냈을 경우
            image_bytes = base64.b64decode(image_data['image'])
            image = Image.open(io.BytesIO(image_bytes))
            print(image)
        else:
            print(2)
            # 사용자가 이미지를 보내지 않았을 경우
            default_image = 'female.webp' if image_data['gender'].lower() == 'female' else 'male.jpg'
            image_path = os.path.join('assets/images/', default_image)
            print(3)
            image = Image.open(image_path)
            print(4,image)
        
        # 이미지 처리 또는 저장
        response = await generate_image_websocket(uid, image)
        print(4)

        print("response : ", response['images'])

        if response['status'] == 'complete':
            images = response['images']
            persona_data = {
                'anger' : images['anger']['image_url'],
                'disgust' : images['disgust']['image_url'],
                'joy' : images['joy']['image_url'],
                'sadness' : images['sadness']['image_url'],
                'serious' : images['serious']['image_url']
            }
            
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


if __name__ == "__main__":
    import uvicorn
    print("FastAPI 서버 실행")
    uvicorn.run(app, host="0.0.0.0", port=1818)

def load_image(file_path):
    if os.path.exists(file_path):
        return Image.open(file_path)
    else:
        print(f"이미지 파일을 찾을 수 없습니다: {file_path}")
        return None
