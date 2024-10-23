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

@app.post("/image-generate-default/{uid}/{gender}")
async def image_generate_default(uid: str, gender: str , image : UploadFile=File(...)):
    print("image_generate_default 호출")
    print(gender)
    print(image)
    if image is None:
        if gender == "male":
            image = load_image('assets/images/male.jpg')
        else:
            image = load_image('assets/images/female.webp')
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


if __name__ == "__main__":
    import uvicorn
    print("FastAPI 서버 실행")
    uvicorn.run(app, host="0.0.0.0", port=1818)