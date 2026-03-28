import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import RegisterView from './RegisterView.vue'

const pushMock = vi.fn()
const registerMock = vi.fn()
const successMock = vi.fn()
const warningMock = vi.fn()
const errorMock = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: pushMock,
  }),
}))

vi.mock('../api/auth', () => ({
  register: (...args: unknown[]) => registerMock(...args),
}))

vi.mock('@arco-design/web-vue', () => ({
  Message: {
    success: (...args: unknown[]) => successMock(...args),
    warning: (...args: unknown[]) => warningMock(...args),
    error: (...args: unknown[]) => errorMock(...args),
  },
}))

vi.mock('../utils/request', () => ({
  getApiErrorMessage: () => '注册失败',
}))

describe('RegisterView', () => {
  beforeEach(() => {
    pushMock.mockReset()
    registerMock.mockReset()
    successMock.mockReset()
    warningMock.mockReset()
    errorMock.mockReset()
  })

  it('submits registration and redirects to /login on success', async () => {
    registerMock.mockResolvedValue({})

    const { container } = render(RegisterView, {
      global: {
        stubs: {
          'a-form': { template: '<form><slot /></form>' },
          'a-form-item': { template: '<div><slot /></div>' },
          'a-input': {
            props: ['modelValue'],
            emits: ['update:modelValue'],
            template:
              '<input :value="modelValue" @input="$emit(\'update:modelValue\', ($event.target as HTMLInputElement).value)" />',
          },
          'a-input-password': {
            props: ['modelValue'],
            emits: ['update:modelValue'],
            template:
              '<input type="password" :value="modelValue" @input="$emit(\'update:modelValue\', ($event.target as HTMLInputElement).value)" />',
          },
          'a-button': { template: '<button type="button"><slot /></button>' },
          'a-link': { template: '<a><slot /></a>' },
        },
      },
    })

    const inputs = container.querySelectorAll('input')

    await fireEvent.update(inputs[0], 'new_user')
    await fireEvent.update(inputs[1], 'new_user@example.com')
    await fireEvent.update(inputs[2], 'abc12345')
    await fireEvent.update(inputs[3], 'abc12345')

    await fireEvent.click(screen.getByRole('button', { name: '注册' }))

    await waitFor(() => {
      expect(registerMock).toHaveBeenCalledWith({
        username: 'new_user',
        email: 'new_user@example.com',
        password: 'abc12345',
      })
    })

    expect(successMock).toHaveBeenCalledWith('注册成功，请登录')
    expect(pushMock).toHaveBeenCalledWith('/login')
  })
})
