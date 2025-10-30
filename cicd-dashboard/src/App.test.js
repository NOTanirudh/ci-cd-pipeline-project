import { render, screen } from '@testing-library/react';
import App from './App';

test('renders dashboard header', () => {
  render(<App />);
  const header = screen.getByText(/CI\/CD Pipeline Dashboard/i);
  expect(header).toBeInTheDocument();
});
