import type { Meta, StoryObj } from '@storybook/react-vite'
import { Bolt, TriangleAlert } from 'lucide-react'
import { Button } from '@/shared/ui/button'

const meta = {
  title: 'Shared/Button',
  component: Button,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
} satisfies Meta<typeof Button>

export default meta

type Story = StoryObj<typeof meta>

export const Variants: Story = {
  render: () => (
    <div className="flex flex-wrap gap-4">
      <Button>Основная</Button>
      <Button variant="secondary" iconLeft={<Bolt className="h-4 w-4" />}>Вторичная</Button>
      <Button variant="ghost">Ghost</Button>
      <Button variant="danger" iconLeft={<TriangleAlert className="h-4 w-4" />}>СТОП</Button>
      <Button disabled>Disabled</Button>
    </div>
  ),
}