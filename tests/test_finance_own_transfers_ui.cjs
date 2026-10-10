// Synthetic display checks, no network or actual accounts.
function testOwnTransfersUI(source) {
  const fragment=source.slice(source.indexOf('function transactionParty('),source.indexOf('function sortHeaders('));
  const ui=new Function(fragment+';return {transactionParty,transferText}')();
  const assert=(ok)=>{if(!ok)throw Error('Own transfer UI mismatch')};
  const row={counter_account_label:'Synthetic savings',counterparty:'Bank name',amount:-4500,
    own_transfer_scope:'between_groups',source_group:'Private',destination_group:'Child'};
  assert(ui.transactionParty(row)==='Synthetic savings');
  assert(ui.transferText(row)==='Naar Synthetic savings · Private → Child');
  assert(ui.transferText({...row,amount:4500}).startsWith('Van '));
  assert(ui.transferText({...row,own_transfer_scope:null})==='');
  assert(source.includes("own_transfer:$('ownTransfer').value"));
  assert(source.includes("['transactionType','subcategory','classification','ownTransfer']"));
}
