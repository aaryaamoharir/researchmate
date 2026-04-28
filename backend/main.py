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

SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# Initialize SQLAlchemy for Database Operations
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
 
class StickyNote(Base):
    __tablename__ = "sticky_notes"
    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(UUID(as_uuid=True), index=True)
    pdf_id     = Column(Integer, ForeignKey("pdfs.id", ondelete="CASCADE"))
    page_number = Column(Integer)
    text       = Column(Text, default="")
    x          = Column(Integer)          # px offset from page left
    y          = Column(Integer)          # px offset from page top
    color_idx  = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
 
    pdf = relationship("PDF")
 
 
# 2. ADD THESE PYDANTIC SCHEMAS (alongside your other response models)
# ─────────────────────────────────────────────────────────────────────────────
 
class StickyNoteCreate(BaseModel):
    pdf_id:      int
    page_number: int
    text:        str = ""
    x:           float
    y:           float
    color_idx:   int = 0
 
class StickyNoteUpdate(BaseModel):
    text:      str | None = None
    x:         int | None = None
    y:         int | None = None
    color_idx: int | None = None
 
class StickyNoteResponse(BaseModel):
    id:          int
    pdf_id:      int
    page_number: int
    text:        str
    x:           int
    y:           int
    color_idx:   int
    created_at:  datetime
 
    model_config = ConfigDict(from_attributes=True)
 
class PDF(Base):
    __tablename__ = "pdfs"
    id = Column(Integer, primary_key = True, index = True)
    user_id = Column(UUID(as_uuid=True), index=True)
    file_name = Column(String)
    storage_path = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    supabase_path = Column(String, nullable=True)  

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
    supabase_path = Column(String, nullable=True)  
    page_number = Column(Integer) 
    summary = Column(String)
    pdf = relationship("PDF", back_populates="pdf_pages")


Base.metadata.create_all(bind=engine)


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
from io import BytesIO

def convert_pdf_to_pages(pdf_path: str, pdf_id: int, user_id: str, file_id: str, db: Session):
    pages = convert_from_path(pdf_path)  # no poppler_path needed on Mac

    page_folder = f"storage/pdfs/{file_id}/pages"
    os.makedirs(page_folder, exist_ok=True)

    for i, page in enumerate(pages, start=1):
        image_file_path = f"{page_folder}/{i}.png"
        page.save(image_file_path, "PNG")

        supabase_page_path = f"{user_id}/{file_id}/pages/{i}.png"
        with open(image_file_path, "rb") as img_file:
            supabase_admin.storage.from_("pdf-pages").upload(  # admin client
                path=supabase_page_path,
                file=img_file.read(),
                file_options={"content-type": "image/png", "upsert": "true"}
            )

        db_page = PDF_Pages(
            pdf_id=pdf_id,
            page_number=i,
            image_path=f"pdfs/{file_id}/pages/{i}.png",
            supabase_path=supabase_page_path,
            summary="empty"
        )
        db.add(db_page)

    db.commit()

#Upload new PDF into Database
@app.post("/pdf/upload", response_model=PDFResponse)
def create_pdf(file: UploadFile = File(...), db: Session = Depends(get_db), current_user = Depends(verify_token)):
    file_id = str(uuid.uuid4())
    folder = f"storage/pdfs/{file_id}"
    os.makedirs(folder, exist_ok=True)
    path = f"{folder}/original.pdf"

    file_bytes = file.file.read()
    with open(path, "wb") as buffer:
        buffer.write(file_bytes)

    supabase_path = f"{current_user['sub']}/{file_id}/original.pdf"
    supabase_admin.storage.from_("pdfs").upload(
        path=supabase_path,
        file=file_bytes,
        file_options={"content-type": "application/pdf", "upsert": "true"}
    )

    pdf = PDF(
        file_name=file.filename,
        storage_path=path,
        supabase_path=supabase_path,
        user_id=uuid.UUID(current_user["sub"])
    )
    db.add(pdf)
    db.commit()
    db.refresh(pdf)

    # Wrap conversion so we can see the real error
    try:
        convert_pdf_to_pages(path, pdf.id, current_user["sub"], file_id, db)
    except Exception as e:
        print(f"❌ convert_pdf_to_pages failed: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Page conversion failed: {str(e)}")

    return pdf

#Get all user pdfs
@app.get("/pdf/my_pdfs", response_model=List[PDFResponse])
def get_my_pdfs(current_user=Depends(verify_token), db: Session = Depends(get_db)):
    pdfs = db.query(PDF).filter(
        PDF.user_id == uuid.UUID(current_user["sub"])
    ).order_by(PDF.created_at.desc()).all()
    return pdfs


#Return list of all PDFS(metadata)
#@app.get("/pdf/", response_model=List[PDFResponse])
#def read_pdfs(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
#    pdfs = db.query(PDF).offset(skip).limit(limit).all()
#    return pdfs

#PDF Page data contracts
class PDFPageResponse(BaseModel):
    id: int
    pdf_id: int
    image_path: str
    page_number: int 
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

#PDF Pages endpoints

#Gets all pages paths
@app.get("/pdf/{id}/pages", response_model=List[PDFPageResponse])
def get_pdf_pages(id : int, db : Session = Depends(get_db), current_user = Depends(verify_token)):
        pdf = db.query(PDF).filter(PDF.id == id).first()
        if pdf is None:
            raise HTTPException(status_code=404, detail="PDF not Found")
        
        if str(pdf.user_id) != current_user["sub"]:
            raise HTTPException(status_code=403, detail="Not authorized to access this PDF")
        
        pages = (db.query(PDF_Pages).filter(PDF_Pages.pdf_id == id).order_by(PDF_Pages.page_number).all())
        return pages

#Get Page PNG image
@app.get("/pdf/{id}/pages/{page_number}")
def get_pdf_page(id: int, page_number: int, db: Session = Depends(get_db), current_user = Depends(verify_token)):
    pdf = db.query(PDF).filter(PDF.id == id).first()
    if pdf is None:
        raise HTTPException(status_code=404, detail="PDF not found")
    if str(pdf.user_id) != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    page = db.query(PDF_Pages).filter(
        PDF_Pages.pdf_id == id,
        PDF_Pages.page_number == page_number
    ).first()
    
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")

    # Try local file first using image_path from DB (not hardcoded)
    local_path = f"storage/{page.image_path}"
    if os.path.exists(local_path):
        return FileResponse(path=local_path, media_type="image/png")

    # Fall back to Supabase signed URL
    if page.supabase_path is None:
        raise HTTPException(status_code=404, detail="No file path available")
    
    signed = supabase_admin.storage.from_("pdf-pages").create_signed_url(
        page.supabase_path, expires_in=3600
    )
    return RedirectResponse(url=signed["signedURL"])

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

 
@app.post("/notes/", response_model=StickyNoteResponse)
def create_note(
    payload: StickyNoteCreate,
    db: Session = Depends(get_db),
    current_user=Depends(verify_token),
):
    """Create a sticky note for the authenticated user."""
    # Verify the PDF belongs to this user
    pdf = db.query(PDF).filter(PDF.id == payload.pdf_id).first()
    if pdf is None:
        raise HTTPException(status_code=404, detail="PDF not found")
    if str(pdf.user_id) != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Not authorized")
 
    note = StickyNote(
        user_id=uuid.UUID(current_user["sub"]),
        pdf_id=payload.pdf_id,
        page_number=payload.page_number,
        text=payload.text,
        x=payload.x,
        y=payload.y,
        color_idx=payload.color_idx,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note
 
 
@app.get("/notes/{pdf_id}", response_model=List[StickyNoteResponse])
def get_notes_for_pdf(
    pdf_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(verify_token),
):
    """Return all sticky notes the current user placed on a specific PDF."""
    pdf = db.query(PDF).filter(PDF.id == pdf_id).first()
    if pdf is None:
        raise HTTPException(status_code=404, detail="PDF not found")
    if str(pdf.user_id) != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Not authorized")
 
    return (
        db.query(StickyNote)
        .filter(
            StickyNote.pdf_id == pdf_id,
            StickyNote.user_id == uuid.UUID(current_user["sub"]),
        )
        .order_by(StickyNote.page_number, StickyNote.id)
        .all()
    )
 
 
@app.patch("/notes/{note_id}", response_model=StickyNoteResponse)
def update_note(
    note_id: int,
    payload: StickyNoteUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(verify_token),
):
    """Update text, position, or colour of a note."""
    note = db.query(StickyNote).filter(StickyNote.id == note_id).first()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    if str(note.user_id) != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Not authorized")
 
    if payload.text      is not None: note.text      = payload.text
    if payload.x         is not None: note.x         = payload.x
    if payload.y         is not None: note.y         = payload.y
    if payload.color_idx is not None: note.color_idx = payload.color_idx
 
    db.commit()
    db.refresh(note)
    return note
 
 
@app.delete("/notes/{note_id}", status_code=204)
def delete_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(verify_token),
):
    """Delete a sticky note."""
    note = db.query(StickyNote).filter(StickyNote.id == note_id).first()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    if str(note.user_id) != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Not authorized")
 
    db.delete(note)
    db.commit()


#background worker
from contextlib import asynccontextmanager
from fastapi import FastAPI
import asyncio
from worker import summary_worker

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(summary_worker())

    yield  # app runs here

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(lifespan=lifespan)

#backup if no work
#@app.on_event("startup")
#async def start_worker():
 #   from worker import summary_worker
  #  import asyncio

   # asyncio.create_task(summary_worker())