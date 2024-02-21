from fastapi import FastAPI, HTTPException, status, Depends, Form
from typing import Annotated
from uuid import UUID
from model.document import Document
import uvicorn
import os
from database import database as database
from sqlalchemy.orm import Session
from keycloak import KeycloakOpenID

app = FastAPI()

app = FastAPI()
database.Base.metadata.create_all(bind=database.engine)

# Данные для подключения к Keycloak
KEYCLOAK_URL = "http://keycloak:8080/"
KEYCLOAK_CLIENT_ID = "boyarkov"
KEYCLOAK_REALM = "myrealm"
KEYCLOAK_CLIENT_SECRET = "T678RfL6Jxtk5zmNQygPAn7ahcTnPzTr"

keycloak_openid = KeycloakOpenID(server_url=KEYCLOAK_URL,
                                  client_id=KEYCLOAK_CLIENT_ID,
                                  realm_name=KEYCLOAK_REALM,
                                  client_secret_key=KEYCLOAK_CLIENT_SECRET)

ser_token = ""


###########
#Prometheus
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app)

@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    try:
        # Получение токена
        token = keycloak_openid.token(grant_type=["password"],
                                      username=username,
                                      password=password)
        global user_token
        user_token = token
        return token
    except Exception as e:
        print(e)  # Логирование для диагностики
        raise HTTPException(status_code=400, detail="Не удалось получить токен")

def check_user_roles():
    global user_token
    token = user_token
    try:
        userinfo = keycloak_openid.userinfo(token["access_token"])
        token_info = keycloak_openid.introspect(token["access_token"])
        if "testRole" not in token_info["realm_access"]["roles"]:
            raise HTTPException(status_code=403, detail="Access denied")
        return token_info
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid token or access denied")

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


db_dependency = Annotated[Session, Depends(get_db)]


@app.get("/health", status_code=status.HTTP_200_OK)
async def doc_health():
    return {'message': 'service is active'}


@app.get("/user_docs")
async def fetch_docs(db: db_dependency):
    result = db.query(database.DBDoc).offset(0).limit(100).all()
    return result


@app.get("/doc_by_id")
async def fetch_docs(owner_id: UUID, db: db_dependency):
    result = db.query(database.DBDoc).filter(database.DBDoc.owner_id == owner_id).first()
    print(owner_id)
    print(result)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f'doc with such owner id is not found. owner_id: {owner_id}'
        )
    return result


@app.post('/add_doc')
async def add_doc(doc: Document, db: db_dependency):
    db_doc = database.DBDoc(
        id=doc.id,
        owner_id=doc.owner_id,
        title=doc.title,
        body=doc.body,
    )
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    return {"id": doc.id}


@app.delete("/delete_document")
async def delete_doc(doc_id: int, db: db_dependency):
    try:
        doc_db = db.query(database.DBDoc).filter(database.DBDoc.id == doc_id).first()
        db.delete(doc_db)
    except Exception:
        return "cant find document"

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv('PORT', 80)))
