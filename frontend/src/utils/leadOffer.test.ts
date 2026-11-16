import { describe, expect, it } from 'vitest'
import { hasLeadOffer } from './leadOffer'

describe('hasLeadOffer', () => {
  it('находит предложение заявки во втором сообщении', () => {
    const reply =
      'Чтобы сократить расходы, выберите ценовую категорию по графику нагрузки.\n\n' +
      'Если хотите, передам заявку менеджеру. Для этого нужны ФИО, телефон и название компании. ' +
      'Напишите «да», и я оформлю заявку.'
    expect(hasLeadOffer(reply)).toBe(true)
  })

  it('возвращает false для обычного ответа консультанта', () => {
    const reply = 'Для вашей ситуации подойдёт тариф с дифференциацией по часам суток.'
    expect(hasLeadOffer(reply)).toBe(false)
  })

  it('возвращает false для пустой строки', () => {
    expect(hasLeadOffer('')).toBe(false)
  })
})
