import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Upload, MessageCircle, Menu, X, FileText, ChevronRight, Loader2, StickyNote, Trash2 } from 'lucide-react';

// ─── Note colors ─────────────────────────────────────────────────────────────
const NOTE_COLORS = [
  { bg: 'rgba(250,230,100,0.88)', border: 'rgba(200,160,20,0.7)',  text: '#2a2000' },
  { bg: 'rgba(140,225,140,0.88)', border: 'rgba(40,160,40,0.7)',   text: '#052005' },
  { bg: 'rgba(160,190,255,0.88)', border: 'rgba(80,110,230,0.7)',  text: '#050530' },
  { bg: 'rgba(255,165,175,0.88)', border: 'rgba(210,60,80,0.7)',   text: '#300010' },
  { bg: 'rgba(210,170,255,0.88)', border: 'rgba(140,60,220,0.7)',  text: '#180030' },
];

// ─── API helpers ──────────────────────────────────────────────────────────────
const API = 'http://localhost:8000';
const authHeaders = () => ({
  'Content-Type': 'application/json',
  Authorization: `Bearer ${localStorage.getItem('access_token')}`,
});

// ─── StickyNoteWidget ─────────────────────────────────────────────────────────
function StickyNoteWidget({ note, onUpdate, onDelete }) {
  const [dragging, setDragging] = useState(false);
  const dragStart = useRef({ mx: 0, my: 0, nx: 0, ny: 0 });
  const saveTimer = useRef(null);
  const c = NOTE_COLORS[note.colorIdx ?? 0];

  const onMouseDown = (e) => {
    if (['TEXTAREA','BUTTON','svg','path','circle'].includes(e.target.tagName)) return;
    e.preventDefault();
    e.stopPropagation();
    setDragging(true);
    dragStart.current = { mx: e.clientX, my: e.clientY, nx: note.x, ny: note.y };
  };

  const onMouseMove = useCallback((e) => {
    if (!dragging) return;
    const dx = e.clientX - dragStart.current.mx;
    const dy = e.clientY - dragStart.current.my;
    onUpdate(note.id, { x: dragStart.current.nx + dx, y: dragStart.current.ny + dy }, false);
  }, [dragging, note.id, onUpdate]);
  // Persist position on drag end
  const onMouseUp = useCallback(() => {
    setDragging(false);
    onUpdate(note.id, { x: note.x, y: note.y }, true);
  }, [note.id, note.x, note.y, onUpdate]);

  useEffect(() => {
    if (dragging) {
      window.addEventListener('mousemove', onMouseMove);
      window.addEventListener('mouseup', onMouseUp);
    }
    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, [dragging, onMouseMove, onMouseUp]);

  // Debounced text save
  const handleTextChange = (e) => {
    const text = e.target.value;
    onUpdate(note.id, { text }, false);          // update local state immediately
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      onUpdate(note.id, { text }, true);         // persist after 600 ms of quiet
    }, 600);
  };

  return (
    <div
      onMouseDown={onMouseDown}
      style={{
        position: 'absolute',
        left: note.x,
        top: note.y,
        width: 190,
        minHeight: 110,
        background: c.bg,
        border: `1.5px solid ${c.border}`,
        borderRadius: 9,
        boxShadow: dragging ? '0 12px 32px rgba(0,0,0,0.35)' : '0 3px 14px rgba(0,0,0,0.22)',
        cursor: dragging ? 'grabbing' : 'grab',
        zIndex: dragging ? 100 : 20,
        display: 'flex',
        flexDirection: 'column',
        backdropFilter: 'blur(3px)',
        userSelect: 'none',
        transform: dragging ? 'scale(1.02)' : 'scale(1)',
        transition: dragging ? 'none' : 'box-shadow 0.15s, transform 0.15s',
        animation: note.fresh ? 'noteIn 0.18s ease both' : undefined,
      }}
    >
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '5px 7px 4px',
        borderBottom: `1px solid ${c.border}`,
        gap: 4,
      }}>
        <div style={{ display: 'flex', gap: 4 }}>
          {NOTE_COLORS.map((col, i) => (
            <button key={i} onClick={() => onUpdate(note.id, { colorIdx: i }, true)} style={{
              width: 10, height: 10, borderRadius: '50%',
              background: col.bg,
              border: note.colorIdx === i ? `2px solid ${c.text}` : `1px solid ${col.border}`,
              cursor: 'pointer', padding: 0, flexShrink: 0,
            }} />
          ))}
        </div>
        <button onClick={() => onDelete(note.id)} style={{
          background: 'none', border: 'none', cursor: 'pointer',
          color: c.text, opacity: 0.45, padding: '1px 2px', lineHeight: 1,
          display: 'flex', alignItems: 'center',
        }}>
          <Trash2 size={11} />
        </button>
      </div>
      {/* Body */}
      <textarea
        autoFocus={note.fresh}
        value={note.text}
        placeholder="Type your note…"
        onChange={handleTextChange}
        style={{
          flex: 1, background: 'transparent', border: 'none', outline: 'none',
          resize: 'none', padding: '7px 9px',
          fontSize: 12, lineHeight: 1.55, color: c.text,
          fontFamily: 'Sora, sans-serif', cursor: 'text', minHeight: 70,
        }}
      />
    </div>
  );
}

// ─── PdfViewer ────────────────────────────────────────────────────────────────
function PdfViewer({ pdfId, notes, noteMode, onPlaceNote, onUpdateNote, onDeleteNote }) {
  const [pages, setPages] = useState([]);
  const [loading, setLoading] = useState(true);
  const containerRef = useRef(null);

  useEffect(() => {
    if (!pdfId) return;
    setLoading(true);
    setPages([]);

    fetch(`${API}/pdf/${pdfId}/pages`, { headers: authHeaders() })
      .then(res => { if (!res.ok) throw new Error(`HTTP ${res.status}`); return res.json(); })
      .then(data => setPages(Array.isArray(data) ? data : []))
      .catch(err => console.error('Failed to load pages:', err))
      .finally(() => setLoading(false));
  }, [pdfId]);

  const handlePageClick = (e, pageIndex, pageNumber) => {
    if (!noteMode) return;
    e.stopPropagation();
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left - 95;
    const y = e.clientY - rect.top - 20;
    onPlaceNote(pageIndex, pageNumber, Math.max(0, x), Math.max(0, y));
  };

  if (loading) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0c0c14' }}>
        <Loader2 size={28} className="spin" style={{ color: '#a78bfa' }} />
      </div>
    );
  }

  return (
    <div ref={containerRef} style={{
      flex: 1, overflowY: 'auto', overflowX: 'hidden',
      background: '#0c0c14', padding: '16px',
      cursor: noteMode ? 'crosshair' : 'default',
    }}>
      {pages.map((page, i) => {
        const pageNotes = notes.filter(n => n.pageIndex === i);
        return (
          <div
            key={page.id}
            onClick={(e) => handlePageClick(e, i, page.page_number)}
            style={{
              position: 'relative', marginBottom: 12, borderRadius: 6,
              overflow: 'hidden', boxShadow: '0 4px 24px rgba(0,0,0,0.45)',
              lineHeight: 0, background: '#fff',
            }}
          >
            <AuthImage
              src={`${API}/pdf/${pdfId}/pages/${page.page_number}`}
              alt={`Page ${page.page_number}`}
              style={{ width: '100%', display: 'block' }}
            />
            {pageNotes.map(note => (
              <StickyNoteWidget
                key={note.id}
                note={note}
                onUpdate={onUpdateNote}
                onDelete={onDeleteNote}
              />
            ))}
          </div>
        );
      })}
    </div>
  );
}

// ─── AuthImage ────────────────────────────────────────────────────────────────
function AuthImage({ src, alt, style }) {
  const [blobUrl, setBlobUrl] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let objectUrl = null;
    fetch(src, { headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` } })
      .then(res => { if (!res.ok) throw new Error(`HTTP ${res.status}`); return res.blob(); })
      .then(blob => { objectUrl = URL.createObjectURL(blob); setBlobUrl(objectUrl); })
      .catch(() => setError(true));
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [src]);

  if (error) return (
    <div style={{ ...style, background: '#1a1a2e', display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 200 }}>
      <span style={{ color: '#55557a', fontSize: 12 }}>Failed to load page</span>
    </div>
  );
  if (!blobUrl) return (
    <div style={{ ...style, background: '#13131d', display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 200 }}>
      <Loader2 size={20} className="spin" style={{ color: '#a78bfa' }} />
    </div>
  );
  return <img src={blobUrl} alt={alt} style={style} />;
}

// ─── DUMMY SUMMARIES (unchanged) ──────────────────────────────────────────────
const DUMMY_SUMMARIES = [
  { section: "Abstract",     summary: "Novel framework for large-scale distributed systems addressing latency and fault-tolerance in cloud-native environments.", page: 1 },
  { section: "Introduction", summary: "Highlights 3× data throughput requirements for modern apps; introduces a new consensus algorithm and adaptive load-balancer.", page: 2 },
  { section: "Related Work", summary: "Surveys Raft, Paxos, ZooKeeper; identifies gaps in partial-failure recovery and cross-region consistency.", page: 4 },
  { section: "Methodology",  summary: "Two-phase commit variant with optimistic locking. Gossip protocol reduces coordination overhead by ~40%.", page: 7 },
  { section: "Evaluation",   summary: "200-node cluster across 3 AWS regions. 99.95% uptime under network partitions; 12 ms median latency — 2.1× better than baseline.", page: 11 },
  { section: "Discussion",   summary: "Limitations in WAN >300 ms RTT. Future: GPU-accelerated consensus for ML workloads.", page: 15 },
  { section: "Conclusion",   summary: "Adaptive consensus + gossip heartbeats significantly improves resilience without sacrificing throughput.", page: 17 },
];

// ─── Dashboard ────────────────────────────────────────────────────────────────
export default function Dashboard() {
  const [uploadedFile, setUploadedFile]     = useState(null);
  const [pdfId, setPdfId]                   = useState(null);
  const [myPdfs, setMyPdfs]                 = useState([]);
  const [sidebarOpen, setSidebarOpen]       = useState(false);
  const [uploading, setUploading]           = useState(false);
  const [chatOpen, setChatOpen]             = useState(false);
  const [chatMessage, setChatMessage]       = useState('');
  const [isDragging, setIsDragging]         = useState(false);
  const [activeFileName, setActiveFileName] = useState('');

  // notes shape: { id (DB id or temp), pageIndex, pageNumber, x, y, text, colorIdx, fresh, synced }
  const [notes, setNotes]         = useState([]);
  const [noteMode, setNoteMode]   = useState(false);
  const [nextColor, setNextColor] = useState(0);
  const [notesLoading, setNotesLoading] = useState(false);

  const fileInputRef = useRef(null);
  const pdfLoaded = !!pdfId;

  useEffect(() => { fetchMyPdfs(); }, []);

  // Load notes from DB whenever active PDF changes
  useEffect(() => {
    setNotes([]);
    setNoteMode(false);
    if (pdfId) loadNotesForPdf(pdfId);
  }, [pdfId]);

  const fetchMyPdfs = async () => {
    try {
      const res = await fetch(`${API}/pdf/my_pdfs`, { headers: authHeaders() });
      if (res.ok) setMyPdfs(await res.json());
    } catch (err) { console.error(err); }
  };

  // ── Note loading ────────────────────────────────────────────────────────────
  const loadNotesForPdf = async (id) => {
    setNotesLoading(true);
    try {
      const res = await fetch(`${API}/notes/${id}`, { headers: authHeaders() });
      if (!res.ok) return;
      const data = await res.json();
      // Map DB records → local shape.
      // pageIndex = page_number - 1  (DB stores 1-based page numbers)
      const mapped = data.map(n => ({
        id:         n.id,
        pageIndex:  n.page_number - 1,
        pageNumber: n.page_number,
        x:          n.x,
        y:          n.y,
        text:       n.text,
        colorIdx:   n.color_idx,
        fresh:      false,
        synced:     true,
      }));
      setNotes(mapped);
    } catch (err) {
      console.error('Failed to load notes:', err);
    } finally {
      setNotesLoading(false);
    }
  };

  // ── Note CRUD with DB sync ──────────────────────────────────────────────────

  /** Called by PdfViewer when the user clicks to place a new note */
  const handlePlaceNote = async (pageIndex, pageNumber, x, y) => {
    // Optimistic local insert with a temp id
    const tempId = `temp-${Date.now()}`;
    const colorIdx = nextColor;
    setNotes(prev => [...prev, {
      id: tempId, pageIndex, pageNumber, x, y,
      text: '', colorIdx, fresh: true, synced: false,
    }]);
    setNextColor(c => (c + 1) % NOTE_COLORS.length);
    setNoteMode(false);

    try {
      const res = await fetch(`${API}/notes/`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          pdf_id:      pdfId,
          page_number: pageNumber,
          text:        '',
          x, y,
          color_idx:   colorIdx,
        }),
      });
      if (!res.ok) throw new Error('Create failed');
      const created = await res.json();
      // Replace temp id with real DB id
      setNotes(current =>
        current.map(n =>
          n.id === tempId
            ? { ...n, id: created.id, synced: true }
            : n
        )
      );
    } catch (err) {
      console.error('Failed to save note:', err);
      // Roll back the optimistic insert
      setNotes(prev => prev.filter(n => n.id !== tempId));
    }
  };

  /**
   * updateNote is called by StickyNoteWidget.
   * `persist = true`  → also PATCH the DB
   * `persist = false` → local state only (e.g. during drag)
   */
  const updateNote = useCallback(async (id, changes, persist) => {
    setNotes(prev => prev.map(n => n.id === id ? { ...n, ...changes, fresh: false } : n));

    if (!persist || String(id).startsWith('temp-')) return;

    try {
      const body = {};
      if (changes.text      !== undefined) body.text      = changes.text;
      if (changes.x         !== undefined) body.x         = changes.x;
      if (changes.y         !== undefined) body.y         = changes.y;
      if (changes.colorIdx  !== undefined) body.color_idx = changes.colorIdx;

      await fetch(`${API}/notes/${id}`, {
        method: 'PATCH',
        headers: authHeaders(),
        body: JSON.stringify(body),
      });
    } catch (err) {
      console.error('Failed to update note:', err);
    }
  }, []);

  const deleteNote = useCallback(async (id) => {
    setNotes(prev => prev.filter(n => n.id !== id));
    if (String(id).startsWith('temp-')) return;
    try {
      await fetch(`${API}/notes/${id}`, { method: 'DELETE', headers: authHeaders() });
    } catch (err) {
      console.error('Failed to delete note:', err);
    }
  }, []);

  const clearAllNotes = async () => {
    const toDelete = notes.filter(n => !String(n.id).startsWith('temp-'));
    setNotes([]);
    await Promise.all(
      toDelete.map(n =>
        fetch(`${API}/notes/${n.id}`, { method: 'DELETE', headers: authHeaders() })
          .catch(err => console.error('Failed to delete note', n.id, err))
      )
    );
  };

  // ── File handling ────────────────────────────────────────────────────────────
  const handleFileUpload = async (file) => {
    if (!file || file.type !== 'application/pdf') return;
    setUploadedFile(file);
    setActiveFileName(file.name);
    setUploading(true);
    try {
      const fd = new FormData(); fd.append('file', file);
      const res = await fetch(`${API}/pdf/upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` },
        body: fd,
      });
      if (!res.ok) { setUploading(false); return; }
      const data = await res.json();
      setPdfId(data.id);
      fetchMyPdfs();
    } catch (err) { console.error(err); }
    finally { setUploading(false); }
  };

  const handleLoadExistingPdf = (pdf) => {
    setPdfId(pdf.id);
    setActiveFileName(pdf.file_name);
    setUploadedFile(null);
    setSidebarOpen(false);
  };

  const handleFileDrop = (e) => {
    e.preventDefault(); setIsDragging(false);
    handleFileUpload(e.dataTransfer.files[0]);
  };

  const handleReset = () => {
    setPdfId(null); setUploadedFile(null); setActiveFileName('');
    setSidebarOpen(false); setNotes([]); setNoteMode(false);
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#0e0e14] text-[#e2e2f0]">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Sora:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        body, button, input, textarea { font-family: 'Sora', sans-serif; }
        @keyframes fadeUp  { from { opacity:0; transform:translateY(14px); } to { opacity:1; transform:translateY(0); } }
        @keyframes spin    { from { transform:rotate(0deg); } to { transform:rotate(360deg); } }
        @keyframes slideIn { from { opacity:0; transform:translateX(-6px); } to { opacity:1; transform:translateX(0); } }
        @keyframes noteIn  { from { opacity:0; transform:scale(0.86) translateY(8px); } to { opacity:1; transform:scale(1) translateY(0); } }
        .fade-up     { animation: fadeUp 0.4s ease both; }
        .fade-up-pdf { animation: fadeUp 0.35s ease both; }
        .spin        { animation: spin 1s linear infinite; }
        .slide-in    { animation: slideIn 0.2s ease both; }
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #2a2a3e; border-radius: 3px; }
        .pdf-item:hover    { background: #1c1c2e !important; }
        .recent-card:hover { border-color: #3a3a5e !important; }
        .mono { font-family: 'JetBrains Mono', monospace; }
        .note-active { background: rgba(167,139,250,0.18) !important; color: #c4b5fd !important; border-color: #a78bfa !important; }
      `}</style>

      {/* ── Sidebar ── */}
      <div className="flex-shrink-0 h-screen overflow-hidden bg-[#13131d] border-r border-[#1a1a28] transition-all duration-300"
        style={{ width: sidebarOpen ? '240px' : '0px' }}>
        <div className="w-[240px] h-full flex flex-col"
          style={{ opacity: sidebarOpen ? 1 : 0, pointerEvents: sidebarOpen ? 'auto' : 'none', transition: 'opacity 0.18s' }}>
          <div className="flex items-center justify-between px-4 pt-[18px] pb-3.5 border-b border-[#1a1a28]">
            <span className="text-[11px] font-semibold uppercase tracking-widest text-[#55557a]">Your Library</span>
            <button className="text-[#606080] hover:text-[#a78bfa] transition-colors p-1" onClick={() => setSidebarOpen(false)}>
              <X size={16} />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-0.5">
            {myPdfs.length === 0
              ? <p className="text-[12px] text-[#44445a] px-2.5 py-2">No PDFs yet.</p>
              : myPdfs.map(pdf => (
                <div key={pdf.id}
                  className="pdf-item slide-in flex items-center gap-2.5 px-2.5 py-2 rounded-lg cursor-pointer transition-colors"
                  style={{ background: pdf.id === pdfId ? '#1c1c2e' : 'transparent' }}
                  onClick={() => handleLoadExistingPdf(pdf)}>
                  <FileText size={13} className="text-[#a78bfa] flex-shrink-0" />
                  <span className="text-[12px] text-[#b0b0d0] truncate">{pdf.file_name}</span>
                </div>
              ))}
          </div>
        </div>
      </div>

      {/* ── Main ── */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">

        {/* Top Bar */}
        <div className="flex items-center gap-3.5 px-5 py-3.5 border-b border-[#1a1a28] flex-shrink-0">
          <button className="text-[#606080] hover:text-[#a78bfa] transition-colors p-1.5 rounded-lg"
            onClick={() => setSidebarOpen(!sidebarOpen)}>
            <Menu size={20} />
          </button>
          <span className="text-[17px] font-semibold tracking-tight text-[#c4b5fd] flex-1">paperwise</span>

          {pdfLoaded && (
            <div className="flex items-center gap-2">
              {notesLoading && (
                <Loader2 size={13} className="spin text-[#7878a8]" />
              )}
              {notes.length > 0 && !notesLoading && (
                <>
                  <span className="mono text-[11px] text-[#7878a8] px-2 py-1 bg-[#13131d] border border-[#1e1e2e] rounded-md">
                    {notes.length} note{notes.length !== 1 ? 's' : ''}
                  </span>
                  <button onClick={clearAllNotes}
                    className="text-[#55557a] hover:text-red-400 p-1.5 rounded-lg border border-[#1e1e2e] hover:border-red-500/30 transition-all"
                    title="Clear all notes">
                    <Trash2 size={13} />
                  </button>
                </>
              )}
              <button
                onClick={() => setNoteMode(m => !m)}
                className={`flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-lg border border-[#252538] text-[#8888b0] hover:border-[#a78bfa] hover:text-[#c4b5fd] transition-all ${noteMode ? 'note-active' : ''}`}>
                <StickyNote size={14} />
                <span>{noteMode ? 'Click PDF to place…' : 'Add note'}</span>
              </button>
              <button
                className="border border-[#252538] text-[#8888b0] hover:border-[#a78bfa] hover:text-[#c4b5fd] text-[12px] px-3 py-1.5 rounded-lg transition-all"
                onClick={handleReset}>
                ← New Upload
              </button>
            </div>
          )}
        </div>

        {!pdfLoaded ? (
          /* ── UPLOAD VIEW ── */
          <div className="flex-1 flex flex-col items-center justify-center px-6 py-10 gap-7 fade-up">
            <div className="text-center">
              <h1 className="text-[34px] font-semibold text-[#e8e8f8] mb-2.5" style={{ letterSpacing: '-0.04em' }}>
                Drop your research here.
              </h1>
              <p className="text-[14px] text-[#55557a] font-light">Upload a PDF and get instant section-by-section summaries.</p>
            </div>

            <div
              className={`w-full max-w-[500px] border-[1.5px] border-dashed rounded-2xl p-11 flex flex-col items-center gap-2.5 cursor-pointer transition-all
                ${isDragging ? 'border-[#a78bfa] bg-[#19142e]' : 'border-[#252538] bg-[#11111b]'}`}
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleFileDrop}>
              {uploading ? (
                <div className="flex flex-col items-center gap-3">
                  <Loader2 size={32} className="spin text-[#a78bfa]" />
                  <p className="text-[13px] text-[#8888b8]">Uploading {uploadedFile?.name}…</p>
                </div>
              ) : (
                <>
                  <div className="w-14 h-14 rounded-2xl bg-[#1a1428] flex items-center justify-center mb-1">
                    <Upload size={26} className="text-[#a78bfa]" />
                  </div>
                  <p className="text-[14px] font-medium text-[#b0a8d8]">Click or drag a PDF to upload</p>
                  <p className="text-[12px] text-[#3a3a58]">PDF files only · Max 50MB</p>
                </>
              )}
              <input ref={fileInputRef} type="file" accept="application/pdf" className="hidden"
                onChange={(e) => handleFileUpload(e.target.files[0])} />
            </div>

            {myPdfs.length > 0 && (
              <div className="w-full max-w-[500px]">
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#3a3a58] mb-2.5">Recent uploads</p>
                <div className="grid grid-cols-2 gap-2">
                  {myPdfs.slice(0, 4).map(pdf => (
                    <div key={pdf.id}
                      className="recent-card flex items-center gap-2.5 bg-[#12121c] border border-[#1c1c2c] rounded-xl px-3.5 py-3 cursor-pointer transition-colors"
                      onClick={() => handleLoadExistingPdf(pdf)}>
                      <FileText size={15} className="text-[#a78bfa] flex-shrink-0" />
                      <span className="text-[12px] text-[#7878a8] truncate">{pdf.file_name}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          /* ── PDF VIEW ── */
          <div className="flex-1 flex overflow-hidden fade-up-pdf">
            <div className="flex-1 flex flex-col overflow-hidden min-w-0">
              <div className="flex items-center gap-2 px-[18px] py-3.5 border-b border-[#1a1a28] flex-shrink-0">
                <FileText size={14} className="text-[#a78bfa]" />
                <span className="text-[12px] font-medium text-[#7878a8] truncate">{activeFileName}</span>
                {noteMode && (
                  <span className="ml-auto text-[11px] text-[#a78bfa]" style={{ animation: 'fadeUp 0.2s ease both' }}>
                    ✦ Click on any page to place a note
                  </span>
                )}
              </div>
              <PdfViewer
                pdfId={pdfId}
                notes={notes}
                noteMode={noteMode}
                onPlaceNote={handlePlaceNote}
                onUpdateNote={updateNote}
                onDeleteNote={deleteNote}
              />
            </div>

            <div className="w-px bg-[#1a1a28] flex-shrink-0" />

            <div className="w-[320px] flex-shrink-0 flex flex-col overflow-hidden bg-[#10101a]">
              <div className="flex items-center gap-2 px-[18px] py-3.5 border-b border-[#1a1a28] flex-shrink-0">
                <span className="text-[12px] font-medium text-[#7878a8]">Section Summaries</span>
              </div>
              <div className="flex-1 overflow-y-auto p-3.5 flex flex-col gap-2.5">
                {DUMMY_SUMMARIES.map((s, i) => (
                  <div key={i} className="bg-[#14141e] border border-[#1c1c2e] rounded-xl p-3.5"
                    style={{ animation: `fadeUp 0.3s ease ${i * 0.05}s both` }}>
                    <div className="flex justify-between items-center mb-1.5">
                      <span className="text-[11px] font-semibold text-[#a78bfa] tracking-wide">{s.section}</span>
                      <span className="mono text-[10px] text-[#3a3a58]">p.{s.page}</span>
                    </div>
                    <p className="text-[12px] leading-[1.7] text-[#7878a8] font-light">{s.summary}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── Chat FAB ── */}
      <div className="fixed bottom-6 right-6 flex flex-col items-end gap-3 z-50">
        {chatOpen && (
          <div className="w-[300px] bg-[#16161f] border border-[#26263a] rounded-2xl overflow-hidden"
            style={{ boxShadow: '0 20px 48px rgba(0,0,0,0.55)', animation: 'fadeUp 0.22s ease both' }}>
            <div className="flex items-center justify-between px-4 py-3.5 border-b border-[#1c1c2e]">
              <span className="text-[12px] font-semibold text-[#c0b8e8]">Ask anything</span>
              <button className="text-[#606080] hover:text-[#a78bfa] transition-colors p-1"
                onClick={() => setChatOpen(false)}><X size={15} /></button>
            </div>
            <div className="px-4 py-5 min-h-[90px]">
              <p className="text-[12px] text-[#3a3a58] italic">
                {pdfLoaded ? `Ask about "${activeFileName}"…` : 'Upload a PDF to start chatting.'}
              </p>
            </div>
            <div className="flex border-t border-[#1c1c2e]">
              <input
                className="flex-1 bg-transparent border-none outline-none text-[#e2e2f0] text-[12px] px-3.5 py-3"
                placeholder="Type a question…"
                value={chatMessage}
                onChange={(e) => setChatMessage(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && setChatMessage('')}
              />
              <button className="bg-[#a78bfa] hover:bg-[#9161f5] text-white px-3.5 flex items-center transition-colors"
                onClick={() => setChatMessage('')}>
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
        <button
          className="w-[46px] h-[46px] rounded-full bg-[#a78bfa] hover:bg-[#9161f5] text-white flex items-center justify-center transition-all hover:scale-105 hover:shadow-[0_10px_28px_rgba(167,139,250,0.45)]"
          style={{ boxShadow: '0 8px 24px rgba(167,139,250,0.35)' }}
          onClick={() => setChatOpen(!chatOpen)}>
          {chatOpen ? <X size={20} /> : <MessageCircle size={20} />}
        </button>
      </div>
    </div>
  );
}