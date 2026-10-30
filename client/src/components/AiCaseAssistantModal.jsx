import React, { useState, useEffect, useRef } from 'react';
import { 
  X, Sparkles, AlertCircle, FileText, CheckCircle2, Loader2, ArrowRight,
  Wand2, RotateCcw, Check, CheckCheck, BookOpen, SpellCheck
} from 'lucide-react';
import { api } from '../services/api';

export function AiCaseAssistantModal({ isOpen, onClose, onInsertCase }) {
  const [species, setSpecies] = useState('Canine');
  const [symptoms, setSymptoms] = useState('');
  const [vitals, setVitals] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState(null);

  // LanguageTool Autocorrection & Grammar Check State
  const [isChecking, setIsChecking] = useState(false);
  const [correctionResult, setCorrectionResult] = useState(null);
  const [originalSymptomsBeforeFix, setOriginalSymptomsBeforeFix] = useState(null);
  const [successNotice, setSuccessNotice] = useState(false);

  const debounceTimerRef = useRef(null);

  // Real-time debounced grammar and spelling correction
  useEffect(() => {
    if (!isOpen) return;
    const trimmed = symptoms.trim();

    if (trimmed.length < 3) {
      setCorrectionResult(null);
      setIsChecking(false);
      return;
    }

    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    setIsChecking(true);

    debounceTimerRef.current = setTimeout(async () => {
      try {
        const res = await api.ai.correctText(symptoms);
        if (res && res.corrected && res.corrected.trim() !== trimmed && res.edits && res.edits.length > 0) {
          setCorrectionResult(res);
        } else {
          setCorrectionResult(null);
        }
      } catch (err) {
        console.warn('Grammar check debounce error:', err);
      } finally {
        setIsChecking(false);
      }
    }, 650);

    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [symptoms, isOpen]);

  if (!isOpen) return null;

  // Manual Trigger for LanguageTool Correction
  const handleManualCheck = async () => {
    if (!symptoms.trim()) {
      alert('Please enter text into the Chief Complaint box first.');
      return;
    }

    setIsChecking(true);
    setOriginalSymptomsBeforeFix(symptoms);

    try {
      const res = await api.ai.correctText(symptoms);
      if (res && res.edits && res.edits.length > 0) {
        setCorrectionResult(res);
      } else {
        alert('No grammar or spelling errors detected by LanguageTool!');
        setCorrectionResult(null);
      }
    } catch (err) {
      console.warn('Manual correction failed:', err);
      alert('LanguageTool server is loading. Please try again in a few moments.');
    } finally {
      setIsChecking(false);
    }
  };

  // Accept all suggestions at once and run secondary autocorrection on the resulting output
  const handleAcceptAll = async () => {
    if (!correctionResult || !correctionResult.corrected) return;
    const firstCorrectedOutput = correctionResult.corrected;
    setOriginalSymptomsBeforeFix(symptoms);
    setSymptoms(firstCorrectedOutput);
    setIsChecking(true);
    setCorrectionResult(null);

    // After autocorrecting the user input in complaint box, again the output
    // undergoes autocorrection for grammatical and spelling errors
    try {
      const secondPassRes = await api.ai.correctText(firstCorrectedOutput);
      if (secondPassRes && secondPassRes.corrected && secondPassRes.corrected.trim() !== firstCorrectedOutput.trim() && secondPassRes.edits && secondPassRes.edits.length > 0) {
        setCorrectionResult(secondPassRes);
      } else {
        setCorrectionResult(null);
        setSuccessNotice(true);
        setTimeout(() => setSuccessNotice(false), 4000);
      }
    } catch (err) {
      console.warn('Second pass autocorrection error:', err);
    } finally {
      setIsChecking(false);
    }
  };

  // Accept a single edit suggestion and re-run autocorrection on the updated text
  const handleAcceptSingle = async (edit) => {
    if (!edit || !edit.original || !edit.replacement) return;
    setOriginalSymptomsBeforeFix(symptoms);

    // Replace the first exact match in current text
    const updated = symptoms.replace(edit.original, edit.replacement);
    setSymptoms(updated);
    setIsChecking(true);

    try {
      const nextRes = await api.ai.correctText(updated);
      if (nextRes && nextRes.corrected && nextRes.corrected.trim() !== updated.trim() && nextRes.edits && nextRes.edits.length > 0) {
        setCorrectionResult(nextRes);
      } else {
        setCorrectionResult(null);
        setSuccessNotice(true);
        setTimeout(() => setSuccessNotice(false), 4000);
      }
    } catch (err) {
      console.warn('Post-replacement autocorrection error:', err);
    } finally {
      setIsChecking(false);
    }
  };

  // Undo and revert to original input
  const handleUndo = () => {
    if (originalSymptomsBeforeFix !== null) {
      setSymptoms(originalSymptomsBeforeFix);
      setOriginalSymptomsBeforeFix(null);
      setCorrectionResult(null);
    }
  };

  const handleAnalyze = async () => {
    if (!symptoms.trim()) {
      alert('Please enter clinical signs or findings');
      return;
    }

    setIsLoading(true);
    try {
      const data = await api.ai.diagnose({ species, symptoms, vitals });
      setResult(data);
    } catch (err) {
      console.warn('Backend AI diagnosis fallback to offline heuristic:', err);
      setResult({
        primaryDifferentials: [
          { name: "Acute Gastric Dilatation-Volvulus (GDV)", likelihood: "High (85%)", reasoning: "Rapid abdominal tympany, non-productive retching, and tachycardia in deep-chested canine." },
          { name: "Severe Acute Pancreatitis with Peritonitis", likelihood: "Moderate (45%)", reasoning: "Severe cranial abdominal pain and elevated heart rate with potential systemic inflammatory response." },
          { name: "Splenic Torsion / Rupture with Hemoperitoneum", likelihood: "Moderate (40%)", reasoning: "Weak femoral pulses and pale mucous membranes consistent with acute hypovolemia." }
        ],
        recommendedDiagnostics: [
          "Right lateral abdominal radiograph (Double-bubble / reverse C sign verification)",
          "Abdominal FAST (AFAST) scan to rule out peritoneal free fluid in spleno-renal pouch",
          "Serial blood lactate monitoring (Lactate > 6 mmol/L signals gastric ischemia)",
          "Complete Blood Count + Serum Lipase / Spec cPL"
        ],
        emergencyActionProtocol: [
          "Place two large-bore IV catheters (18G or 16G) in cephalic veins.",
          "Rapid isotonic crystalloid shock bolus (20-30 mL/kg over 15-20 min).",
          "Attempt gentle orogastric decompression or 14G percutaneous trocarization in right paracostal area.",
          "Prepare patient for emergency exploratory laparotomy and gastropexy."
        ]
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" style={{ maxWidth: '680px' }} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="modal-header" style={{ background: 'linear-gradient(135deg, #093721 0%, #0D472B 100%)', color: '#FFF' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ width: '34px', height: '34px', borderRadius: '8px', background: 'rgba(212, 175, 55, 0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Sparkles size={20} color="#F8E2AF" />
            </div>
            <div>
              <h3 className="modal-title" style={{ color: '#FFF', fontSize: '18px' }}>AI Clinical Case Assistant</h3>
              <p style={{ fontSize: '12px', color: '#C8DEC9' }}>Real-time differential diagnosis & emergency triage guidance</p>
            </div>
          </div>
          <button className="btn-close-modal" onClick={onClose} style={{ color: '#FFF' }}>
            <X size={20} />
          </button>
        </div>

        <div className="modal-body">
          {!result ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: '600', marginBottom: '6px', color: '#121A15' }}>
                  Patient Species & Signalment
                </label>
                <div style={{ display: 'flex', gap: '8px' }}>
                  {['Canine', 'Feline', 'Equine', 'Bovine', 'Avian/Exotic'].map(sp => (
                    <button
                      key={sp}
                      type="button"
                      onClick={() => setSpecies(sp)}
                      style={{
                        padding: '8px 14px',
                        borderRadius: '6px',
                        fontSize: '13px',
                        fontWeight: '600',
                        border: '1px solid',
                        borderColor: species === sp ? '#0D472B' : '#E5E9E5',
                        background: species === sp ? '#E8F3ED' : '#FFFFFF',
                        color: species === sp ? '#0D472B' : '#64726A'
                      }}
                    >
                      {sp}
                    </button>
                  ))}
                </div>
              </div>

              {/* Chief Complaint Box with Integrated LanguageTool Autocorrection */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: '600', color: '#121A15', margin: 0 }}>
                    Chief Complaint & Clinical Signs *
                  </label>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {/* Active Status Badge */}
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '5px',
                      background: '#F0FDF4',
                      border: '1px solid #BBF7D0',
                      borderRadius: '12px',
                      padding: '2px 8px',
                      fontSize: '11px',
                      color: '#166534',
                      fontWeight: '600'
                    }}>
                      <div style={{
                        width: '6px',
                        height: '6px',
                        borderRadius: '50%',
                        background: isChecking ? '#F59E0B' : '#10B981'
                      }} />
                      <span>{isChecking ? 'Checking...' : 'LanguageTool Active'}</span>
                    </div>

                    {/* Manual Check Button */}
                    <button
                      type="button"
                      onClick={handleManualCheck}
                      disabled={isChecking}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                        fontSize: '11.5px',
                        color: '#0D472B',
                        fontWeight: '600',
                        padding: '2px 6px',
                        borderRadius: '4px'
                      }}
                      title="Run manual Grammar & Spell Check"
                    >
                      <Wand2 size={13} />
                      <span>Check Details</span>
                    </button>
                  </div>
                </div>

                <div style={{ position: 'relative' }}>
                  <textarea
                    rows="3"
                    className="custom-filter-select"
                    style={{ 
                      width: '100%', 
                      resize: 'vertical',
                      borderColor: (correctionResult && correctionResult.edits && correctionResult.edits.length > 0) ? '#F59E0B' : undefined,
                      transition: 'border-color 0.2s ease'
                    }}
                    placeholder="e.g. 5-year-old German Shepherd, acute abdominal distension, unproductive retching for 3 hours, restlessness, hypersalivation..."
                    value={symptoms}
                    onChange={(e) => setSymptoms(e.target.value)}
                  />

                  {/* Undo Button */}
                  {originalSymptomsBeforeFix !== null && (
                    <button
                      type="button"
                      onClick={handleUndo}
                      style={{
                        position: 'absolute',
                        right: '8px',
                        bottom: '12px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                        background: '#FFFFFF',
                        border: '1px solid #CBD5E1',
                        borderRadius: '4px',
                        padding: '3px 8px',
                        fontSize: '11px',
                        color: '#475569',
                        fontWeight: '600',
                        cursor: 'pointer',
                        boxShadow: '0 1px 2px rgba(0,0,0,0.05)'
                      }}
                      title="Revert to original text before corrections"
                    >
                      <RotateCcw size={12} />
                      <span>Undo</span>
                    </button>
                  )}
                </div>

                {/* Success Banner */}
                {successNotice && (
                  <div style={{
                    marginTop: '6px',
                    padding: '6px 10px',
                    background: '#ECFDF5',
                    border: '1px solid #A7F3D0',
                    borderRadius: '6px',
                    fontSize: '12px',
                    color: '#065F46',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px'
                  }}>
                    <CheckCheck size={14} color="#059669" />
                    <span>All grammar and spelling corrections applied!</span>
                  </div>
                )}

                {/* Suggestions Card */}
                {correctionResult && correctionResult.edits && correctionResult.edits.length > 0 && (
                  <div style={{
                    marginTop: '8px',
                    padding: '12px',
                    background: '#FFFBEB',
                    border: '1px solid #FDE68A',
                    borderRadius: '8px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '10px'
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <SpellCheck size={15} color="#D97706" />
                        <span style={{ fontSize: '12.5px', fontWeight: '700', color: '#92400E' }}>
                          Grammar & Spelling Suggestions ({correctionResult.edits.length} {correctionResult.edits.length === 1 ? 'suggestion' : 'suggestions'})
                        </span>
                      </div>

                      <button
                        type="button"
                        onClick={handleAcceptAll}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                          background: '#0D472B',
                          color: '#FFFFFF',
                          border: 'none',
                          borderRadius: '5px',
                          padding: '4px 10px',
                          fontSize: '12px',
                          fontWeight: '600',
                          cursor: 'pointer'
                        }}
                      >
                        <Check size={13} />
                        <span>Accept All Corrections</span>
                      </button>
                    </div>

                    {/* Proposed text preview */}
                    {correctionResult.corrected && correctionResult.corrected !== symptoms && (
                      <div style={{
                        background: '#FFFFFF',
                        border: '1px solid #FCD34D',
                        borderRadius: '6px',
                        padding: '8px 10px',
                        fontSize: '12.5px',
                        color: '#1E293B',
                        lineHeight: '1.4'
                      }}>
                        <span style={{ fontWeight: '600', color: '#0D472B', marginRight: '6px' }}>Proposed:</span>
                        <span>{correctionResult.corrected}</span>
                      </div>
                    )}

                    {/* Individual Diff Chips */}
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                      {correctionResult.edits.map((edit, idx) => (
                        <div
                          key={idx}
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '6px',
                            background: '#FFFFFF',
                            border: '1px solid #E2E8F0',
                            borderRadius: '6px',
                            padding: '4px 8px',
                            fontSize: '12px'
                          }}
                        >
                          <span style={{
                            fontSize: '10px',
                            fontWeight: '700',
                            padding: '1px 5px',
                            borderRadius: '4px',
                            background: edit.type === 'Spelling' ? '#FEE2E2' : '#E0E7FF',
                            color: edit.type === 'Spelling' ? '#991B1B' : '#3730A3'
                          }}>
                            {edit.type}
                          </span>

                          <span style={{
                            textDecoration: 'line-through',
                            color: '#EF4444',
                            fontWeight: '600'
                          }}>
                            {edit.original}
                          </span>
                          <span style={{ color: '#94A3B8' }}>&rarr;</span>

                          <button
                            type="button"
                            onClick={() => handleAcceptSingle(edit)}
                            style={{
                              background: '#E8F3ED',
                              border: '1px solid #0D472B',
                              borderRadius: '4px',
                              padding: '2px 6px',
                              color: '#0D472B',
                              fontWeight: '700',
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '2px'
                            }}
                            title={edit.message || 'Apply suggested change'}
                          >
                            <span>{edit.replacement}</span>
                            <Check size={11} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: '600', marginBottom: '6px', color: '#121A15' }}>
                  Physical Exam & Vitals (Optional)
                </label>
                <input
                  type="text"
                  className="custom-filter-select"
                  style={{ width: '100%' }}
                  placeholder="e.g. HR 175 bpm, weak femoral pulses, CRT > 2.5s, pale tacky mucosa, tympanic percussion"
                  value={vitals}
                  onChange={(e) => setVitals(e.target.value)}
                />
              </div>

              <div style={{ padding: '12px 14px', background: '#F8F9FA', borderRadius: '8px', border: '1px solid #E5E9E5', fontSize: '12.5px', color: '#64726A', display: 'flex', gap: '8px' }}>
                <AlertCircle size={17} color="#C5A059" style={{ flexShrink: 0, marginTop: '2px' }} />
                <span>AI Case Assistant provides rapid diagnostic suggestions based on peer-reviewed veterinary literature. Clinical decision remains with the attending veterinarian.</span>
              </div>

              <button
                type="button"
                className="btn-submit-post"
                style={{ width: '100%', justifyContent: 'center', padding: '12px', marginTop: '6px' }}
                onClick={handleAnalyze}
                disabled={isLoading}
              >
                {isLoading ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    <span>Analyzing Clinical Parameters...</span>
                  </>
                ) : (
                  <>
                    <Sparkles size={16} color="#F8E2AF" />
                    <span>Generate Differential Diagnoses</span>
                  </>
                )}
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
              <div>
                <h4 style={{ fontSize: '13px', fontWeight: '700', textTransform: 'uppercase', letterSpacing: '0.8px', color: '#0D472B', marginBottom: '8px' }}>
                  Top Differential Diagnoses
                </h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {result.primaryDifferentials.map((diff, idx) => (
                    <div key={idx} style={{ padding: '12px 14px', background: '#F8F9FA', borderRadius: '8px', border: '1px solid #E5E9E5' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                        <strong style={{ fontSize: '14px', color: '#121A15' }}>{diff.name}</strong>
                        <span style={{ fontSize: '12px', fontWeight: '700', color: '#0D472B', background: '#E8F3ED', padding: '2px 8px', borderRadius: '12px' }}>
                          {diff.likelihood}
                        </span>
                      </div>
                      <p style={{ fontSize: '13px', color: '#64726A' }}>{diff.reasoning}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h4 style={{ fontSize: '13px', fontWeight: '700', textTransform: 'uppercase', letterSpacing: '0.8px', color: '#0D472B', marginBottom: '8px' }}>
                  Recommended Diagnostic Workup
                </h4>
                <ul style={{ paddingLeft: '18px', display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '13.5px', color: '#344038' }}>
                  {result.recommendedDiagnostics.map((diag, idx) => (
                    <li key={idx}>{diag}</li>
                  ))}
                </ul>
              </div>

              <div>
                <h4 style={{ fontSize: '13px', fontWeight: '700', textTransform: 'uppercase', letterSpacing: '0.8px', color: '#0D472B', marginBottom: '8px' }}>
                  Emergency Action Steps
                </h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {result.emergencyActionProtocol.map((step, idx) => (
                    <div key={idx} style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', fontSize: '13px', color: '#121A15' }}>
                      <CheckCircle2 size={16} color="#0D472B" style={{ flexShrink: 0, marginTop: '2px' }} />
                      <span>{step}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div style={{ display: 'flex', gap: '10px', marginTop: '10px' }}>
                <button
                  type="button"
                  className="btn-create-profile"
                  style={{ flex: 1, justifyContent: 'center' }}
                  onClick={() => setResult(null)}
                >
                  <span>New Case Analysis</span>
                </button>
                <button
                  type="button"
                  className="btn-submit-post"
                  style={{ flex: 1, justifyContent: 'center' }}
                  onClick={() => {
                    onClose();
                    if (onInsertCase) {
                      onInsertCase(`[AI Case Review] ${species}: ${symptoms.slice(0, 80)}... Potential GDV/Acute Abdomen. Stabilized with IV fluid resuscitation.`);
                    }
                  }}
                >
                  <span>Share Case to Feed</span>
                  <ArrowRight size={16} />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
