import React, { useState } from 'react';
import { Upload, MessageCircle } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';


export default function Dashboard() {
  const [uploadedFile, setUploadedFile] = useState(null);
  const [pdfId, setPdfId] = useState(null);

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file || file.type !== 'application/pdf') return;
  
    setUploadedFile(file);
  
    try {
      const formData = new FormData();
      formData.append('file', file);
  
      const token = localStorage.getItem('access_token');
  
      const response = await fetch('http://localhost:8000/pdf/upload', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          // Note: do NOT set Content-Type here — the browser sets it automatically for FormData
        },
        body: formData,
      });
  
      if (!response.ok) {
        const errorData = await response.json();
        console.error('Upload failed:', errorData.detail);
        return;
      }
  
      const data = await response.json();
      console.log('Upload successful, PDF id:', data.id);
  
      // Save the pdf id so you can request a summary later
      setPdfId(data.id);
  
    } catch (err) {
      console.error('Something went wrong:', err);
    }
  };

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Left Side - PDF Upload */}
      <div className="w-1/2 border-r border-gray-200 flex flex-col items-center justify-center p-8">
        <div className="w-full max-w-md">
          <h2 className="text-2xl font-semibold text-gray-800 mb-6 text-center">
            Upload PDF
          </h2>
          
          <label
            htmlFor="pdf-upload"
            className="flex flex-col items-center justify-center w-full h-64 border-2 border-dashed border-gray-300 rounded-lg cursor-pointer bg-white hover:bg-gray-50 transition-colors"
          >
            <div className="flex flex-col items-center justify-center pt-5 pb-6">
              <Upload className="w-12 h-12 text-gray-400 mb-4" />
              <p className="mb-2 text-sm text-gray-500">
                <span className="font-semibold">Click to upload</span> or drag and drop
              </p>
              <p className="text-xs text-gray-400">PDF files only</p>
            </div>
            <input
              id="pdf-upload"
              type="file"
              className="hidden"
              accept=".pdf"
              onChange={handleFileUpload}
            />
          </label>

          {uploadedFile && (
            <div className="mt-4 p-4 bg-green-50 border border-green-200 rounded-lg">
              <p className="text-sm text-green-800">
                <span className="font-semibold">Uploaded:</span> {uploadedFile.name}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Right Side - Chat Interface */}
      <div className="w-1/2 flex flex-col items-center justify-center p-8 bg-white">
        <div className="flex flex-col items-center">
          <div className="w-16 h-16 bg-blue-500 rounded-full flex items-center justify-center mb-4">
            <MessageCircle className="w-8 h-8 text-white" />
          </div>
          <p className="text-gray-400 text-sm">Start a conversation</p>
        </div>
      </div>
    </div>
  );
}