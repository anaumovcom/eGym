import { Slot } from '@radix-ui/react-slot'
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { cn } from '@/shared/lib/cn'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  asChild?: boolean
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  iconLeft?: ReactNode
}

const variants = {
  primary:
    'sand-glow bg-linear-to-r from-[#b5852f] via-[#d6b05f] to-[#aa7b26] text-[#1b1303] hover:brightness-105',
  secondary:
    'border border-white/10 bg-white/6 text-white hover:border-[#d6b05f]/60 hover:bg-white/10',
  ghost: 'text-white/70 hover:bg-white/6 hover:text-white',
  danger:
    'bg-linear-to-r from-[#811b14] via-[#d33024] to-[#b81a16] text-white hover:brightness-110',
} as const

export function Button({ asChild, className, variant = 'primary', iconLeft, children, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : 'button'

  return (
    <Comp
      className={cn(
        'inline-flex min-h-12 items-center justify-center gap-3 rounded-2xl px-5 py-3 text-sm font-semibold transition duration-200 disabled:pointer-events-none disabled:opacity-50',
        variants[variant],
        className,
      )}
      {...props}
    >
      {iconLeft}
      {children}
    </Comp>
  )
}