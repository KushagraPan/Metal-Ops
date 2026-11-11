// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Select } from './select'

afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})

const testOptions = [
  { value: 'adc12', label: 'ADC12' },
  { value: 'lm6', label: 'LM6' },
  { value: 'long', label: 'H-2026-002 · ADC12 · 1,950.00 kg sellable' },
  { value: 'disabled-opt', label: 'Disabled Option', disabled: true },
]

describe('Select Component', () => {
  it('renders and allows selection by click', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(
      <Select
        id="test-alloy"
        label="Alloy"
        value="adc12"
        options={testOptions}
        onChange={onChange}
      />,
    )

    const trigger = screen.getByRole('button', { name: /Alloy/i })
    expect(trigger).toBeDefined()
    expect(trigger.textContent).toContain('ADC12')

    await user.click(trigger)
    const option = await screen.findByRole('option', { name: /LM6/i })
    await user.click(option)

    expect(onChange).toHaveBeenCalledWith('lm6')
  })

  it('supports full keyboard navigation (arrows, Enter, Escape) and returns focus to trigger', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(
      <Select
        id="test-alloy-kb"
        label="Alloy Selection"
        value="adc12"
        options={testOptions}
        onChange={onChange}
      />,
    )

    const trigger = screen.getByRole('button', { name: /Alloy Selection/i })
    await user.click(trigger)
    expect(screen.getByRole('listbox')).toBeDefined()

    // Navigate with ArrowDown and select with Enter
    await user.keyboard('{ArrowDown}')
    await user.keyboard('{Enter}')
    expect(onChange).toHaveBeenCalledWith('lm6')

    // Re-open and test Escape closes without selecting and returns focus to trigger
    await user.click(trigger)
    expect(screen.getByRole('listbox')).toBeDefined()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('listbox')).toBeNull()
    expect(document.activeElement).toBe(trigger)
  })

  it('associates with an external label via htmlFor and id', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(
      <div>
        <label htmlFor="external-select-id">External Label</label>
        <Select
          id="external-select-id"
          label="External Label"
          value="adc12"
          options={testOptions}
          onChange={onChange}
        />
      </div>,
    )

    const trigger = screen.getByLabelText('External Label')
    expect(trigger).toBeDefined()
    expect(trigger.tagName).toBe('BUTTON')

    // Clicking the label should focus or open the listbox
    await user.click(screen.getByText('External Label'))
    expect(screen.getByRole('listbox')).toBeDefined()
  })

  it('respects disabled state on the whole control and individual options', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    const { rerender } = render(
      <Select
        id="disabled-select"
        label="Disabled Select"
        value="adc12"
        options={testOptions}
        onChange={onChange}
        disabled={true}
      />,
    )

    const trigger = screen.getByRole('button', { name: /Disabled Select/i })
    expect(trigger.getAttribute('disabled')).not.toBeNull()

    // Enabled select with a disabled option
    rerender(
      <Select
        id="disabled-select"
        label="Select with disabled option"
        value="adc12"
        options={testOptions}
        onChange={onChange}
        disabled={false}
      />,
    )

    const enabledTrigger = screen.getByRole('button', {
      name: /Select with disabled option/i,
    })
    await user.click(enabledTrigger)
    const disabledOption = await screen.findByRole('option', {
      name: /Disabled Option/i,
    })
    expect(disabledOption.getAttribute('aria-disabled')).toBe('true')
  })

  it('renders native select below md breakpoint (< 768px)', () => {
    const originalWidth = window.innerWidth
    try {
      window.innerWidth = 375
      render(
        <Select
          id="mobile-select"
          label="Mobile Mode"
          value="adc12"
          options={testOptions}
          onChange={() => {}}
        />,
      )

      const nativeSelect = screen.getByRole('combobox')
      expect(nativeSelect.tagName).toBe('SELECT')
      expect(nativeSelect.id).toBe('mobile-select')
    } finally {
      window.innerWidth = originalWidth
    }
  })
})

