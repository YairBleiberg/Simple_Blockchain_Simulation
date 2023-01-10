from .utils import BlockHash
from .transaction import Transaction
from typing import List
import hashlib

class Block:
    # implement __init__ as you see fit.

    def __init__(self, prev_block_hash: BlockHash, transactions: List[Transaction]) -> None:
        #args is either (List[transactions],prev_block_hash) or (List[transactions]), for initial block
        self.transactions: List[Transaction] = transactions
        self.prev_block_hash: BlockHash = prev_block_hash


    def get_block_hash(self) -> BlockHash:
        """returns hash of this block"""
        h = hashlib.sha256()
        h.update(self.prev_block_hash)
        for transaction in self.transactions:
            transaction.get_txid()
            h.update(transaction.get_txid())
        return BlockHash(h.digest())


    def get_transactions(self) -> List[Transaction]:
        """returns the list of transactions in this block."""
        return self.transactions

    def get_prev_block_hash(self) -> BlockHash:
        """Gets the hash of the previous block in the chain"""
        return self.prev_block_hash
