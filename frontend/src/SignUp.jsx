import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

export default function SignUp() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSignUp = async (e) => {
    e.preventDefault();
    setError('');
    if (!name || !email || !password || !confirmPassword) {
      setError('Please fill in all fields');
      return;
    }
    if (password.length < 6) {
      setError('Password must be at least 6 characters');
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }
    setLoading(true);
    try {
      const response = await fetch('http://localhost:8000/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, password }),
      });
      if (!response.ok) {
        const errorData = await response.json();
        setError(errorData.detail || 'Failed to create account');
        setLoading(false);
        return;
      }
      const data = await response.json();
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('user_id', data.user_id);
      localStorage.setItem('user_name', data.name);
      navigate('/dashboard');
    } catch (err) {
      setError('Something went wrong. Please try again.');
      setLoading(false);
    }
  };


  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#0e0e14] font-sans">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Sora:wght@300;400;500;600&family=DM+Serif+Display:ital@0;1&display=swap');
        body { font-family: 'Sora', sans-serif; }
        .serif { font-family: 'DM Serif Display', serif; }
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(18px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes float {
          0%, 100% { transform: translateY(0px); }
          50%       { transform: translateY(-10px); }
        }
        .fade-up { animation: fadeUp 0.45s ease both; }
        .fade-up-slow { animation: fadeUp 0.6s ease 0.3s both; }
        .float-1 { animation: float 6s ease-in-out infinite; }
        .float-2 { animation: float 5s ease-in-out infinite 0.5s; }
        .float-3 { animation: float 6s ease-in-out infinite 1.5s; }
        .auth-input:focus { border-color: #a78bfa !important; box-shadow: 0 0 0 3px rgba(167,139,250,0.15); }
      `}</style>

      {/* ── Left: Form Panel ── */}
      <div className="w-[45%] flex-shrink-0 flex items-center justify-center px-10 py-12 border-r border-[#1a1a28]">
        <div className="w-full max-w-[400px] fade-up">

          {/* Brand */}
          <div className="flex items-center gap-3 mb-8">
            <div className="w-10 h-10 rounded-xl bg-[#1a1428] border border-[#2a2040] flex items-center justify-center flex-shrink-0">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path d="M9 12h6M9 16h6M7 4H5a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2V6a2 2 0 00-2-2h-2M9 4a2 2 0 012-2h2a2 2 0 012 2v0a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                  stroke="#a78bfa" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <span className="text-xl font-semibold tracking-tight text-[#c4b5fd]">researchMate</span>
          </div>

          {/* Heading */}
          <div className="mb-7">
            <h2 className="serif text-[28px] text-[#e8e8f8] mb-1.5">Create your account</h2>
            <p className="text-[13px] text-[#55557a] font-light">Start reading research smarter today</p>
          </div>

          {/* Form */}
          <form onSubmit={handleSignUp} className="flex flex-col gap-[18px]">
            <div className="flex flex-col gap-1.5">
              <label className="text-[12px] font-medium text-[#7878a8] tracking-wide">Full Name</label>
              <input
                className="auth-input w-full bg-[#13131d] border border-[#252538] rounded-[10px] px-3.5 py-3 text-[13px] text-[#e2e2f0] outline-none transition-all"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="John Doe"
                style={{ fontFamily: 'Sora, sans-serif' }}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-[12px] font-medium text-[#7878a8] tracking-wide">Email Address</label>
              <input
                className="auth-input w-full bg-[#13131d] border border-[#252538] rounded-[10px] px-3.5 py-3 text-[13px] text-[#e2e2f0] outline-none transition-all"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                style={{ fontFamily: 'Sora, sans-serif' }}
              />
            </div>

            {/* Password row — side by side */}
            <div className="flex gap-3">
              <div className="flex flex-col gap-1.5 flex-1">
                <label className="text-[12px] font-medium text-[#7878a8] tracking-wide">Password</label>
                <input
                  className="auth-input w-full bg-[#13131d] border border-[#252538] rounded-[10px] px-3.5 py-3 text-[13px] text-[#e2e2f0] outline-none transition-all"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  style={{ fontFamily: 'Sora, sans-serif' }}
                />
              </div>
              <div className="flex flex-col gap-1.5 flex-1">
                <label className="text-[12px] font-medium text-[#7878a8] tracking-wide">Confirm Password</label>
                <input
                  className="auth-input w-full bg-[#13131d] border border-[#252538] rounded-[10px] px-3.5 py-3 text-[13px] text-[#e2e2f0] outline-none transition-all"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="••••••••"
                  style={{ fontFamily: 'Sora, sans-serif' }}
                />
              </div>
            </div>

            {error && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-3.5 py-2.5">
                <p className="text-[12px] text-red-400">{error}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-[#a78bfa] hover:bg-[#9161f5] text-white font-semibold text-[14px] py-3 rounded-[10px] mt-0.5 transition-all hover:-translate-y-px hover:shadow-[0_8px_24px_rgba(167,139,250,0.4)] active:translate-y-0 disabled:opacity-70 cursor-pointer"
              style={{ fontFamily: 'Sora, sans-serif' }}
            >
              {loading ? 'Creating account…' : 'Create Account'}
            </button>
          </form>

          {/* Footer */}
          <div className="mt-6 pt-5 border-t border-[#1a1a28] text-center">
            <span className="text-[13px] text-[#44445a]">Already have an account? </span>
            <Link to="/signin" className="text-[13px] font-semibold text-[#a78bfa] hover:text-[#c4b5fd] transition-colors">
              Sign in
            </Link>
          </div>
        </div>
      </div>

      {/* ── Right: Decorative Panel ── */}
      <div className="flex-1 relative flex flex-col items-center justify-center overflow-hidden"
        style={{ background: 'linear-gradient(135deg, #11111c 0%, #160f2a 50%, #0f0f1e 100%)' }}>

        {/* Ambient orbs */}
        <div className="float-1 absolute top-[5%] right-0 w-[300px] h-[300px] rounded-full pointer-events-none"
          style={{ background: 'radial-gradient(circle, rgba(167,139,250,0.16) 0%, transparent 70%)' }} />
        <div className="float-2 absolute bottom-[10%] left-[5%] w-[220px] h-[220px] rounded-full pointer-events-none"
          style={{ background: 'radial-gradient(circle, rgba(139,92,246,0.13) 0%, transparent 70%)' }} />
        <div className="float-3 absolute top-[50%] right-[15%] w-[150px] h-[150px] rounded-full pointer-events-none"
          style={{ background: 'radial-gradient(circle, rgba(196,181,253,0.1) 0%, transparent 70%)' }} />

        {/* Illustration */}
        <div className="relative w-[300px] h-[260px]" style={{ animation: 'fadeUp 0.55s ease 0.15s both' }}>
          {/* Steps card */}
          <div className="absolute top-2.5 left-1/2 -translate-x-1/2 w-[240px] bg-[#16161f] border border-[#2a2040] rounded-2xl p-5"
            style={{ boxShadow: '0 24px 64px rgba(0,0,0,0.5)' }}>
            <p className="text-[11px] font-semibold uppercase tracking-widest text-[#55557a] mb-3.5">Get started in seconds</p>
            {[
              { icon: '⬆', label: 'Upload your PDF' },
              { icon: '✦', label: 'AI reads every section' },
              { icon: '◎', label: 'Get instant summaries' },
            ].map((step, i) => (
              <div key={i} className="flex items-center gap-2.5 py-2 border-b border-[#1a1a28] last:border-0">
                <span className="text-[12px] text-[#a78bfa] w-5 text-center flex-shrink-0">{step.icon}</span>
                <span className="text-[13px] text-[#b0b0d0] flex-1">{step.label}</span>
                <span className="text-[11px] font-semibold text-[#a78bfa]">✓</span>
              </div>
            ))}
          </div>

          {/* Stat chip */}
          <div className="float-2 absolute bottom-5 -right-3.5 bg-[#1c1630] border border-[#3a2a5e] rounded-xl p-3 flex items-center gap-2.5"
            style={{ boxShadow: '0 8px 32px rgba(0,0,0,0.4)' }}>
            <div className="w-7 h-7 rounded-lg flex-shrink-0" style={{ background: 'linear-gradient(135deg, #a78bfa, #7c3aed)' }} />
            <div>
              <p className="text-[16px] font-semibold text-[#c4b5fd] leading-none mb-0.5">∞</p>
              <p className="text-[11px] text-[#7878a8]">Papers supported</p>
            </div>
          </div>

          {/* Tag chip */}
          <div className="float-3 absolute top-0 -right-5 bg-[#a78bfa]/10 border border-[#a78bfa]/25 rounded-full px-3 py-1.5">
            <span className="text-[11px] font-medium text-[#c4b5fd]">✦ Free to start</span>
          </div>
        </div>

        {/* Tagline */}
        <div className="absolute bottom-10 text-center px-10 fade-up-slow">
          <p className="serif text-[22px] text-[#c4b5fd] mb-2">Your research, distilled.</p>
          <p className="text-[13px] text-[#44445a] font-light">Join researchers who read papers in half the time.</p>
        </div>
      </div>
    </div>
  );
}