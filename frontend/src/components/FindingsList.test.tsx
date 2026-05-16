import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import FindingsList from './FindingsList';

const makeFinding = (override: Partial<{
  clause_type: string;
  risk_level: string;
  extracted_value: string;
  deviation: string;
  playbook_standard: string;
  recommendation: string;
  source_text: string;
}> = {}) => ({
  clause_type: 'payment_terms',
  risk_level: 'medium',
  extracted_value: '30 days',
  deviation: 'Within standard',
  playbook_standard: '30-60 days',
  recommendation: 'No action required.',
  source_text: 'Pay within 30 days of invoice.',
  retrieved_chunks: [],
  ...override,
});

describe('FindingsList', () => {
  it('renders empty state message when list is empty', () => {
    render(<FindingsList findings={[]} />);
    expect(screen.getByText(/No findings yet/)).toBeTruthy();
  });

  it('renders clause type label for each finding', () => {
    render(<FindingsList findings={[makeFinding({ clause_type: 'retainage' })]} />);
    expect(screen.getByText(/retainage/i)).toBeTruthy();
  });

  it('renders risk_level badge', () => {
    render(<FindingsList findings={[makeFinding({ risk_level: 'critical' })]} />);
    expect(screen.getByText('critical')).toBeTruthy();
  });

  it('applies left border color for critical risk', () => {
    const { container } = render(<FindingsList findings={[makeFinding({ risk_level: 'critical' })]} />);
    const card = container.querySelector('.finding-card') as HTMLElement;
    expect(card.style.borderLeft).toBeTruthy();
  });

  it('applies left border color for low risk', () => {
    const { container } = render(<FindingsList findings={[makeFinding({ risk_level: 'low' })]} />);
    const card = container.querySelector('.finding-card') as HTMLElement;
    expect(card.style.borderLeft).toBeTruthy();
  });

  it('finding body is hidden by default (collapsed)', () => {
    render(<FindingsList findings={[makeFinding()]} />);
    expect(screen.queryByText('No action required.')).toBeNull();
  });

  it('expands finding body on header click', () => {
    render(<FindingsList findings={[makeFinding()]} />);
    const header = screen.getByTitle('Click to expand');
    fireEvent.click(header);
    expect(screen.getByText('No action required.')).toBeTruthy();
  });

  it('collapses finding on second click', () => {
    render(<FindingsList findings={[makeFinding()]} />);
    const header = screen.getByTitle('Click to expand');
    fireEvent.click(header);
    fireEvent.click(screen.getByTitle('Click to collapse'));
    expect(screen.queryByText('No action required.')).toBeNull();
  });

  it('sorts findings so critical comes before low', () => {
    const findings = [
      makeFinding({ clause_type: 'warranty', risk_level: 'low' }),
      makeFinding({ clause_type: 'indemnification', risk_level: 'critical' }),
    ];
    const { container } = render(<FindingsList findings={findings} />);
    const cards = container.querySelectorAll('.finding-card strong');
    expect(cards[0].textContent).toBe('indemnification');
    expect(cards[1].textContent).toBe('warranty');
  });

  it('expand all button label toggles after click', () => {
    render(<FindingsList findings={[makeFinding()]} />);
    const btn = screen.getByText('Expand all');
    fireEvent.click(btn);
    expect(screen.getByText('Collapse all')).toBeTruthy();
  });

  it('renders multiple findings', () => {
    const findings = [
      makeFinding({ clause_type: 'payment_terms', risk_level: 'high' }),
      makeFinding({ clause_type: 'retainage', risk_level: 'medium' }),
      makeFinding({ clause_type: 'force_majeure', risk_level: 'low' }),
    ];
    render(<FindingsList findings={findings} />);
    expect(screen.getByText('payment terms')).toBeTruthy();
    expect(screen.getByText('retainage')).toBeTruthy();
    expect(screen.getByText('force majeure')).toBeTruthy();
  });

  it('shows severity count chips when findings present', () => {
    const findings = [
      makeFinding({ risk_level: 'high' }),
      makeFinding({ risk_level: 'high' }),
      makeFinding({ risk_level: 'low' }),
    ];
    render(<FindingsList findings={findings} />);
    expect(screen.getByText('2 high')).toBeTruthy();
    expect(screen.getByText('1 low')).toBeTruthy();
  });

  it('expand all button expands all findings', () => {
    const findings = [
      makeFinding({ clause_type: 'payment_terms', recommendation: 'rec-one' }),
      makeFinding({ clause_type: 'retainage', recommendation: 'rec-two' }),
    ];
    render(<FindingsList findings={findings} />);
    fireEvent.click(screen.getByText('Expand all'));
    expect(screen.getByText('rec-one')).toBeTruthy();
    expect(screen.getByText('rec-two')).toBeTruthy();
  });

  it('displays confidence percentage when provided', () => {
    render(<FindingsList findings={[makeFinding({ confidence: 0.85 } as any)]} />);
    fireEvent.click(screen.getByTitle('Click to expand'));
    expect(screen.getByText('85%')).toBeTruthy();
  });

  it('calls onClear when Clear button clicked', () => {
    const onClear = vi.fn();
    render(<FindingsList findings={[makeFinding()]} onClear={onClear} />);
    fireEvent.click(screen.getByText('Clear'));
    expect(onClear).toHaveBeenCalledOnce();
  });
});
