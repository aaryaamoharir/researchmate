const API_BASE = "http://127.0.0.1:8000";

//gets current user token
function getToken() {
  return localStorage.getItem("access_token");
}

function authHeaders() {
  return {
    Authorization: `Bearer ${getToken()}`
  };
}
//Sign up function, calls backend to store login
export async function signup(email, password, name) {
  const res = await fetch(`${API_BASE}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, name })
  });

  if (!res.ok) throw new Error("Signup failed");

  const data = await res.json();
  localStorage.setItem("access_token", data.access_token);

  return data;
}
//Login function, calls backend to store login 
export async function login(email, password){
    const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password})
  });
  if (!res.ok) throw new Error("Login failed");

  const data = await res.json();
  localStorage.setItem("access_token", data.access_token);

  return data;
}
//getting user
export async function getCurrentUser(){
    const res = await fetch(`${API_BASE}/auth/me`, {
        headers: authHeaders()
    });
    if (!res.ok) throw new Error("Failed to fetch User");

    return res.json();

}

//PDF Functions

//Upload PDFs
export async function uploadPDF(file){
    const formData = new FormData(file); 
    formData.append("file", file);

    const res = await fetch(`${API_BASE}/pdf/upload`, {
        method: "POST",
        headers: {
        Authorization: `Bearer ${getToken()}`
        },
        body: formData});

    if (!res.ok) throw new Error("Failed to upload File");

    return res.json();

}

//Get Current Users PDFs
export async function getMyPDFs() {
  const res = await fetch(`${API_BASE}/pdf/my_pdfs`, {
    headers: authHeaders()
  });

  if (!res.ok) throw new Error("Failed to fetch PDFs");

  return res.json();
}
