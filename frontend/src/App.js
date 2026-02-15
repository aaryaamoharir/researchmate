
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import SignIn from "./SignIn"; 
import SignUp from "./SignUp";

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<SignIn />} />
        <Route path="/signin" element={<SignIn />} />
        <Route path="/signup" element={<SignUp />} />
      </Routes>
    </Router>
  );
}
