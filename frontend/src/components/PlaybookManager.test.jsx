import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import PlaybookManager, { ACTIVE_VERSION_STORAGE_KEY } from './PlaybookManager';
import axios from 'axios';

vi.mock('axios');

const mockVersions = [
  {
    id: '7f187ff4-d8e2-48e9-9518-b3455094e726',
    version_label: '2025-12-28',
    content: 'latest content',
  },
  {
    id: 'ddec771b-2324-40bf-a812-da14beaa784b',
    version_label: '1.0',
    content: 'older content',
  },
];

describe('PlaybookManager', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    localStorage.clear();
  });

  it('restores the persisted active version when available', async () => {
    localStorage.setItem(ACTIVE_VERSION_STORAGE_KEY, mockVersions[1].id);
    axios.get.mockResolvedValue({ data: mockVersions });
    const onVersionChange = vi.fn();

    render(<PlaybookManager apiBase="/api" onVersionChange={onVersionChange} />);

    await waitFor(() => expect(screen.getByText(`Active #${mockVersions[1].id}`)).toBeInTheDocument());
    expect(onVersionChange).toHaveBeenCalledWith(mockVersions[1].id);
    expect(screen.getByDisplayValue(mockVersions[1].content)).toBeInTheDocument();
  });

  it('switches active version when "Use for analysis" is clicked and persists selection', async () => {
    axios.get.mockResolvedValue({ data: mockVersions });
    const onVersionChange = vi.fn();

    render(<PlaybookManager apiBase="/api" onVersionChange={onVersionChange} />);

    await waitFor(() => expect(screen.getByText(`Active #${mockVersions[0].id}`)).toBeInTheDocument());
    const useButtons = screen.getAllByText('Use for analysis');
    fireEvent.click(useButtons[1]);

    await waitFor(() => expect(screen.getByText(`Active #${mockVersions[1].id}`)).toBeInTheDocument());
    expect(onVersionChange).toHaveBeenLastCalledWith(mockVersions[1].id);
    expect(localStorage.getItem(ACTIVE_VERSION_STORAGE_KEY)).toBe(mockVersions[1].id);
    expect(screen.getByDisplayValue(mockVersions[1].content)).toBeInTheDocument();
  });
});