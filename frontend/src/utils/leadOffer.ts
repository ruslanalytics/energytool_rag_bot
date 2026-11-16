export const LEAD_OFFER_PHRASE = 'передам заявку менеджеру'

export function hasLeadOffer(reply: string): boolean {
  return reply.includes(LEAD_OFFER_PHRASE)
}
