import type { Preview } from '@storybook/react-vite'
import { MemoryRouter } from 'react-router-dom'
import '../src/app/styles.css'

const preview: Preview = {
  decorators: [
    (Story) => (
      <MemoryRouter>
        <div className="min-h-screen bg-[#05080f] p-6 text-white">
          <Story />
        </div>
      </MemoryRouter>
    ),
  ],
  parameters: {
    layout: 'fullscreen',
    backgrounds: {
      default: 'forma-dark',
      values: [{ name: 'forma-dark', value: '#05080f' }],
    },
  },
}

export default preview