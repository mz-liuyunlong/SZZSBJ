/** Keep delayed requests from ever showing data under another selected account. */

export interface AccountRequestTicket {
  account: string;
  generation: number;
}

export function createNewProductAccountGuard() {
  let currentAccount = "";
  let generation = 0;

  return {
    selectAccount(account: string): void {
      currentAccount = account;
      generation += 1;
    },
    begin(account: string): AccountRequestTicket {
      generation += 1;
      return { account, generation };
    },
    isCurrent(ticket: AccountRequestTicket): boolean {
      return ticket.account === currentAccount && ticket.generation === generation;
    },
    invalidate(): void {
      generation += 1;
    },
  };
}
