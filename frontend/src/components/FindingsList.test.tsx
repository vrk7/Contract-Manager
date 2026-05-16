import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
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
  it('renders "No findings yet." when list is empty', () => {
    render(<FindingsList findings={[]} />);
    expect(screen.getByText('No findings yet.')).toBeTruthy();
  });

  it('renders clause type label for each finding', () => {
    render(<FindingsList findings={[makeFinding({ clause_type: 'retainage' })]} />);
    expect(screen.getByText('retainage')).toBeTruthy();
  });

  it('renders risk_level badge', () => {
    render(<FindingsList findings={[makeFinding({ risk_level: 'critical' })]} />);
    expect(screen.getByText('critical')).toBeTruthy();
  });

  it('applies left border color for critical risk', () => {
    const { container } = render(<FindingsList findings={[makeFinding({ risk_level: 'critical' })]} />);
    const card = container.querySelector('.finding-card') as HTMLElement;
    expect(card.style.borderLeft).toContain('#e53e3e');
  });

  it('applies left border color for low risk', () => {
    const { container } = render(<FindingsList findings={[makeFinding({ risk_level: 'low' })]} />);
    const card = container.querySelector('.finding-card') as HTMLElement;
    expect(card.style.borderLeft).toContain('#38a169');
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

  it('renders multiple findings', () => {
    const findings = [
      makeFinding({ clause_type: 'payment_terms', risk_level: 'high' }),
      makeFinding({ clause_type: 'retainage', risk_level: 'medium' }),
      makeFinding({ clause_type: 'force_majeure', risk_level: 'low' }),
    ];
    render(<FindingsList findings={findings} />);
    expect(screen.getByText('payment_terms')).toBeTruthy();
    expect(screen.getByText('retainage')).toBeTruthy();
    expect(screen.getByText('force_majeure')).toBeTruthy();
  });
});
