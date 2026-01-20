import React, { useEffect, useState } from 'react';
import axios from 'axios';

export const ACTIVE_VERSION_STORAGE_KEY = 'activePlaybookVersionId';

interface PlaybookVersion {
  id: string;
  version_label: string;
  content: string;
  change_note?: string;
  created_at?: string;
}

interface PlaybookManagerProps {
  apiBase: string;
  onVersionChange?: (versionId: string) => void;
}

export default function PlaybookManager({ apiBase, onVersionChange }: PlaybookManagerProps) {
  const [current, setCurrent] = useState<PlaybookVersion | null>(null);
  const [versions, setVersions] = useState<PlaybookVersion[]>([]);
  const [editorContent, setEditorContent] = useState<string>('');
  const [changeNote, setChangeNote] = useState<string>('');
  const [saving, setSaving] = useState<boolean>(false);

  const setActiveVersion = (versionId: string, availableVersions: PlaybookVersion[] = versions) => {
    const selected = availableVersions.find((v) => v.id === versionId);
    if (!selected) {
      return;
    }
    setCurrent(selected);
    setEditorContent(selected.content || '');
    localStorage.setItem(ACTIVE_VERSION_STORAGE_KEY, selected.id);
    onVersionChange?.(selected.id);
  };

  const load = async (preferredVersionId?: string) => {
    const list = await axios.get<PlaybookVersion[]>(`${apiBase}/playbook/versions`);
    const fetchedVersions = list.data || [];
    setVersions(fetchedVersions);

    if (fetchedVersions.length === 0) {
      setCurrent(null);
      setEditorContent('');
      return;
    }

    const storedVersionId = localStorage.getItem(ACTIVE_VERSION_STORAGE_KEY);
    const candidateId =
      (preferredVersionId && fetchedVersions.some((v) => v.id === preferredVersionId) && preferredVersionId) ||
      (storedVersionId && fetchedVersions.some((v) => v.id === storedVersionId) && storedVersionId) ||
      fetchedVersions[0].id;

    setActiveVersion(candidateId, fetchedVersions);
  };

  useEffect(() => {
    load();
  }, []);

  const save = async () => {
    setSaving(true);
    const resp = await axios.put<{ id: string }>(`${apiBase}/playbook`, {
      content: editorContent,
      change_note: changeNote,
    });
    setSaving(false);
    setChangeNote('');
    await load(resp.data.id);
  };

  const reindex = async (versionId: string) => {
    await axios.post(`${apiBase}/playbook/reindex`, { version_id: versionId });
    await load(versionId);
  };

  const handleUseForAnalysis = (versionId: string) => {
    setActiveVersion(versionId);
  };

  return (
    <div>
      <div className="card-header">
        <div>
          <p className="eyebrow">Governance</p>
          <h3>Playbook</h3>
          <p className="muted">Edit, version, and reindex your contract playbook.</p>
        </div>
        {current?.id && <span className="pill">Active #{current.id}</span>}
      </div>
      <textarea value={editorContent} onChange={(e) => setEditorContent(e.target.value)} />
      <div className="meta-row">
        <input
          placeholder="Change note"
          value={changeNote}
          onChange={(e) => setChangeNote(e.target.value)}
          className="input text"
        />
        <button onClick={save} disabled={saving}>
          {saving ? 'Saving…' : 'Save new version'}
        </button>
      </div>
      <h4>Versions</h4>
      <ul className="version-list">
        {versions.map((v) => (
          <li key={v.id} className="version-row">
            <div>
              <strong>#{v.id}</strong> <span className="muted">({v.version_label})</span>
            </div>
            <div className="pill-group">
              <button onClick={() => handleUseForAnalysis(v.id)}>Use for analysis</button>
              <button onClick={() => reindex(v.id)} className="ghost">
                Reindex
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
