from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import UUID
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime
import uuid
from uuid import UUID as PyUUID
import shutil
import fitz
import os
from dotenv import load_dotenv
from supabase import create_client, Client
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import FileResponse
from jose import jwt, JWTError
from pdf2image import convert_from_path
from PIL import Image


from fastapi.middleware.cors import CORSMiddleware





app = FastAPI()

# Add this right after app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

load_dotenv()

# Initialize Supabase client for Authentication
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize SQLAlchemy for Database Operations
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class PDF(Base):
    __tablename__ = "pdfs"
    id = Column(Integer, primary_key = True, index = True)
    user_id = Column(UUID(as_uuid=True), index=True)
    file_name = Column(String)
    storage_path = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    summaries = relationship("Summary", back_populates="pdf")
    pdf_pages = relationship("PDF_Pages", back_populates="pdf")

class Summary(Base):
    __tablename__ = "summaries"
    id = Column(Integer, primary_key = True, index = True)
    pdf_id = Column(Integer, ForeignKey("pdfs.id"))
    summary = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    pdf = relationship("PDF", back_populates="summaries")
    #Create a model used var as well

class PDF_Pages(Base):
    __tablename__ = "pdf_pages"
    id = Column(Integer, primary_key = True, index = True)
    pdf_id = Column(Integer, ForeignKey("pdfs.id"))
    image_path = Column(String) #where to store the images
    created_at = Column(DateTime, default=datetime.utcnow)
    pdf = relationship("PDF", back_populates="pdf_pages")


# Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

#User Data Contracts wuth User Auth
class SignUpRequest(BaseModel):
    email: str
    password: str
    name: str

class LoginRequest(BaseModel):
    email: str
    password: str

class AuthResponse(BaseModel):
    access_token: str
    user_id: str
    email: str
    name: str

class UserProfileResponse(BaseModel):
    id: str
    email: str
    name: str
    created_at: str

#Helper function for token verification
def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Verify token using Supabase Auth API.
    """
    try:
        token = credentials.credentials
        
        print("=" * 60)
        print("TOKEN VERIFICATION DEBUG")
        print("=" * 60)
        print(f"Token received (first 50): {token[:50]}...")
        print(f"Token length: {len(token)}")
        
        # Try to get user from Supabase
        print("Calling supabase.auth.get_user()...")
        user_response = supabase.auth.get_user(token)
        
        print(f"Response type: {type(user_response)}")
        print(f"Has user: {hasattr(user_response, 'user')}")
        
        if user_response and user_response.user:
            print(f"✅ User found: {user_response.user.email}")
            print("=" * 60)
            
            return {
                "sub": str(user_response.user.id),
                "email": user_response.user.email,
                "user_metadata": user_response.user.user_metadata or {}
            }
        else:
            print("❌ No user in response")
            print(f"Full response: {user_response}")
            print("=" * 60)
            raise HTTPException(status_code=401, detail="Invalid token - no user found")
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Exception occurred: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        print("=" * 60)
        raise HTTPException(
            status_code=401,
            detail=f"Token verification failed: {str(e)}"
        )
  
@app.post("/auth/signup", response_model=AuthResponse)
def signup(signup_data: SignUpRequest):

        # use sign up with supabase
        auth_response = supabase.auth.sign_up({
            "email": signup_data.email,
            "password": signup_data.password,
            "options": {
                "data": {
                    "name": signup_data.name  # store name in database
                }
            }
        })
        
        if not auth_response.user: #error if no work
            raise HTTPException(status_code=400, detail="Failed to create user")
        
        user_name = auth_response.user.user_metadata.get("name", "")
        
        return AuthResponse(
            access_token=auth_response.session.access_token,
            user_id=str(auth_response.user.id),
            email=auth_response.user.email,
            name=user_name
        )

@app.post("/auth/login", response_model=AuthResponse)
def login(login_data: LoginRequest):
    
    try: #checks to see if user is real or not(in databse)
        auth_response = supabase.auth.sign_in_with_password({
            "email": login_data.email,
            "password": login_data.password
        })
        
        if not auth_response.user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Get name from user metadata
        user_name = auth_response.user.user_metadata.get("name", "")
        
        return AuthResponse(
            access_token=auth_response.session.access_token,
            user_id=str(auth_response.user.id),
            email=auth_response.user.email,
            name=user_name
        )
    
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid credentials")


@app.get("/auth/me", response_model=UserProfileResponse)
def get_current_user(current_user = Depends(verify_token)):
    
    return UserProfileResponse(
        id=current_user["sub"],
        email=current_user["email"],
        name=current_user["user_metadata"].get("name", ""),
        created_at=str(datetime.utcnow())  # Or get from token if available
    )
    

#PDF Data Contracts
class PDFResponse(BaseModel):
    id : int
    file_name : str
    user_id: PyUUID
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
     
#Convertion method, turn pdf into png
def convert_pdf_to_pages(pdf_path: str, pdf_id: int, db: Session):
    pages = convert_from_path(pdf_path)

    page_folder = f"storage/pdfs/{pdf_id}/pages"
    os.makedirs(page_folder, exist_ok=True)

    for i, page in enumerate(pages, start=1):
        image_file_path = f"{page_folder}/{i}.png"

        # save image
        page.save(image_file_path, "PNG")

        # save page in DB
        db_page = PDF_Pages(
            pdf_id=pdf_id,
            page_number=i,
            image_path=f"pdfs/{pdf_id}/pages/{i}.png"
        )

        db.add(db_page)

    db.commit()

#Upload new PDF into Database
@app.post("/pdf/upload", response_model=PDFResponse)
def create_pdf(file : UploadFile = File(...), db: Session = Depends(get_db), current_user = Depends(verify_token)):
    file_id = str(uuid.uuid4())
    

    folder = f"storage/pdfs/{file_id}"
    os.makedirs(folder, exist_ok=True)
    
    path = f"{folder}/original.pdf"

    with open(path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    #using user id from supabase auth
    pdf = PDF(file_name = file.filename, 
              storage_path = path, 
              user_id=current_user["sub"]
              )

    db.add(pdf)
    db.commit()
    db.refresh(pdf)
    #conversion method called when uploaded
    convert_pdf_to_pages(path, pdf.id, db)

    return pdf

#Get all user pdfs
@app.get("/pdf/my_pdfs", response_model=List[PDFResponse])
def get_my_pdfs(current_user = Depends(verify_token), db: Session = Depends(get_db), skip: int = 0, limit: int = 10):

    pdfs = db.query(PDF).filter(
        PDF.user_id == current_user["sub"]
    ).offset(skip).limit(limit).all()
    return pdfs


#Return list of all PDFS(metadata)
#@app.get("/pdf/", response_model=List[PDFResponse])
#def read_pdfs(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
#    pdfs = db.query(PDF).offset(skip).limit(limit).all()
#    return pdfs

#Return certain PDF data with the user id
@app.get("/pdf/{id}", response_model=PDFResponse)
def read_pdf(id : int, db : Session = Depends(get_db), current_user = Depends(verify_token)):
    pdf = db.query(PDF).filter(PDF.id == id).first()
    if pdf is None:
        raise HTTPException(status_code=404, detail="PDF not Found")
    
    if str(pdf.user_id) != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Not authorized to access this PDF")
    
    return pdf
    

#Return the actual file as a download
@app.get("/pdf/{id}/download", response_model=PDFResponse)
def get_pdf(id : int, db : Session = Depends(get_db), current_user = Depends(verify_token)):
    pdf = db.query(PDF).filter(PDF.id == id).first()
    if pdf is None:
        raise HTTPException(status_code=404, detail="PDF not Found")
    
    if str(pdf.user_id) != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Not authorized to access this PDF")
    
    return FileResponse(
        path=pdf.storage_path,
        media_type="application/pdf",
        filename=pdf.file_name 
    )

#PDF Pages endpoints
@app.get("/pdf/{id}/pages", response_model=PDFResponse)
def get_pdf_pages(pdf_id : int, db : Session = Depends(get_db), current_user = Depends(verify_token)):
        pdf = db.query(PDF).filter(PDF.id == pdf_id).first()
        if pdf is None:
            raise HTTPException(status_code=404, detail="PDF not Found")
        
        if str(pdf.user_id) != current_user["sub"]:
            raise HTTPException(status_code=403, detail="Not authorized to access this PDF")
        
        pages = (db.query(PDF_Pages).filter(PDF_Pages.pdf_id == pdf_id).order_by(PDF_Pages.id).all())
        return pages





#Summary Data Contracts
class SummaryRequest(BaseModel):
    pdf_id : int


class SummaryResponse(BaseModel):
    id : int
    pdf_id : int
    summary : str
    created_at : datetime

    model_config = ConfigDict(from_attributes=True)

#Langgraph Data Contracts
class LGSummaryInput(BaseModel): #input to AI as text of pdf
    text: str

class LGSummaryOutput(BaseModel): #output the summary of given text
    summary: str

def run_summary_agent(pdf_id: int) -> str: #AI Work, RAG model here
    return "PlaceHold Summary"

#def extract_text_from_pdf(path: str) -> str: not needed
 #   text = ""
  #  with fitz.open(path) as doc:
   #     for page in doc:
    #        text += page.get_text()
    # return text

@app.post("/summary/", response_model=SummaryResponse)
def create_summary(summary_request : SummaryRequest, db : Session = Depends(get_db), current_user = Depends(verify_token)):
    pdf = db.query(PDF).filter(PDF.id == summary_request.pdf_id).first()
    if pdf is None:
        raise HTTPException(status_code=404, detail="PDF not Found")
    
   #text = extract_text_from_pdf(pdf.storage_path) #getting text from the pdf file
    if str(pdf.user_id) != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Not authorized to access this PDF")
    
    # generate summary
    generated_summary = run_summary_agent(pdf.id)

    summary = Summary(
        pdf_id=summary_request.pdf_id,
        summary=generated_summary
    )

    db.add(summary)
    db.commit()
    db.refresh(summary)
    
    return SummaryResponse(id = summary.id, pdf_id = summary.pdf_id, summary = summary.summary, created_at = summary.created_at)

@app.get("/summary/{pdf_id}", response_model=SummaryResponse)
def get_summary(pdf_id : int, db : Session = Depends(get_db), current_user = Depends(verify_token)):

    pdf = db.query(PDF).filter(PDF.id == pdf_id).first()
    if pdf is None:
        raise HTTPException(status_code=404, detail="PDF not Found")
    
    if str(pdf.user_id) != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Not authorized to access this PDF")
    
    summary = db.query(Summary).filter(Summary.pdf_id == pdf_id).first()
    
    if summary is None:
        raise HTTPException(status_code=404, detail="Summary not Found")
    
    return summary
