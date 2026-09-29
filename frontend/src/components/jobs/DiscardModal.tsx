import { useState } from "react";
import { DISCARD_REASONS } from "../../utils/constants";
import type { Job } from "../../types/job";

interface Props {
  job: Job | null;
  saving: boolean;
  onClose: () => void;
  onConfirm: (reason: string, note: string) => void;
}

export function DiscardModal({ job, saving, onClose, onConfirm }: Props) {
  const [reason, setReason] = useState<string>(DISCARD_REASONS[0]);
  const [note, setNote] = useState("");

  if (!job) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>Descartar oferta</h3>
        <p className="modal-sub">
          {job.title}
          {job.company ? ` — ${job.company}` : ""}. Se conserva en la base
          de datos con su motivo para análisis posterior.
        </p>
        <div className="field">
          <label htmlFor="discard-reason">Motivo</label>
          <select
            id="discard-reason"
            className="select"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          >
            {DISCARD_REASONS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="discard-note">Observación (opcional)</label>
          <textarea
            id="discard-note"
            className="textarea"
            placeholder='Ej: "Requiere 3+ años de experiencia…"'
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </div>
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onClose} disabled={saving}>
            Cancelar
          </button>
          <button
            className="btn btn-primary"
            disabled={saving}
            onClick={() => onConfirm(reason, note)}
          >
            {saving ? "Guardando…" : "Descartar"}
          </button>
        </div>
      </div>
    </div>
  );
}
