import { fireEvent, render, screen } from "@testing-library/react";

import CallSentimentTable from "./CallSentimentTable";


describe("CallSentimentTable", () => {
  test("renders empty-state message when no rows exist", () => {
    render(<CallSentimentTable rows={[]} onSelect={() => {}} />);

    expect(screen.getByText(/No records yet/i)).toBeInTheDocument();
  });

  test("calls onSelect with transcript id when row button is clicked", () => {
    const onSelect = vi.fn();
    const rows = [
      {
        transcript_id: 101,
        file_name: "sample_call.txt",
        detailed_insight: "Parent asked about admissions",
        summary: "Summary",
        label: "neutral",
        score: 0.0,
        admission_probability: 55,
        intent_category: "Inquiry",
        intent_score: 3,
        visit_intent: "maybe",
        created_at: "2026-04-10T06:00:00.000Z",
      },
    ];

    render(<CallSentimentTable rows={rows} onSelect={onSelect} />);

    fireEvent.click(screen.getByRole("button", { name: /sample_call\.txt/i }));
    expect(onSelect).toHaveBeenCalledWith(101);
  });
});
