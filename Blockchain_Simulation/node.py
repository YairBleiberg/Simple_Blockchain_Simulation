from .utils import *
from .block import Block
from .transaction import Transaction
from typing import Set, Optional, List, Dict
import secrets

class Node:
    def __init__(self) -> None:
        """Creates a new node with an empty mempool and no connections to others.
        Blocks mined by this node will reward the miner with a single new coin,
        created out of thin air and associated with the mining reward address"""
        keytuple = gen_keys()
        self.privatekey: PrivateKey = keytuple[0]
        self.publickey: PublicKey = keytuple[1]
        self.balance: List[TxID] = []
        self.latest_hash: BlockHash = GENESIS_BLOCK_PREV
        self.blockchain: List[Block] = []
        self.mempool: List[Transaction] = []
        self.utxo: List[Transaction] = []
        self.connections: Set[Node] = set([])
        self.txid_to_transaction: Dict[TxID,Transaction] = {}


    def connect(self, other: 'Node') -> None:
        """connects this node to another node for block and transaction updates.
        Connections are bi-directional, so the other node is connected to this one as well.
        Raises an exception if asked to connect to itself.
        The connection itself does not trigger updates about the mempool,
        but nodes instantly notify of their latest block to each other (see notify_of_block)"""
        if other.get_address() == self.get_address():
            raise ValueError()
        self.connections.add(other)
        other.connections.add(self)

        self.notify_of_block(other.get_latest_hash(), other)
        other.notify_of_block(self.get_latest_hash(), self)

    def disconnect_from(self, other: 'Node') -> None:
        """Disconnects this node from the other node. If the two were not connected, then nothing happens"""
        if other in self.connections:
            self.connections.remove(other)
            other.connections.remove(self)

    def get_connections(self) -> Set['Node']:
        """Returns a set containing the connections of this node."""
        return self.connections

    def add_transaction_to_mempool(self, transaction: Transaction) -> bool:
        """
        This function inserts the given transaction to the mempool.
        It will return False iff any of the following conditions hold:
        (i) the transaction is invalid (the signature fails)
        (ii) the source doesn't have the coin that it tries to spend
        (iii) there is contradicting tx in the mempool.

        If the transaction is added successfully, then it is also sent to neighboring nodes.
        """

        if transaction.input in [t.input for t in self.get_mempool()]:
            return False

        source_address = None
        trans_exists = False

        # This also takes care of coinbase transactions not being allowed into mempool - otherwise trans_exists will be false
        for t in self.get_utxo():
            if t.get_txid() == transaction.input:
                source_address = t.output
                trans_exists = True
                break

        if not trans_exists:
            return False

        if not verify(transaction.output+transaction.input, transaction.signature, source_address):
            return False

        self.mempool.append(transaction)
        for node in self.get_connections():
            if transaction not in node.get_mempool():
                node.add_transaction_to_mempool(transaction)
        self.txid_to_transaction[transaction.get_txid()] = transaction
        return True

    def notify_of_block(self, block_hash: BlockHash, sender: 'Node') -> None:
        """This method is used by a node's connection to inform it that it has learned of a
        new block (or created a new block). If the block is unknown to the current Node, The block is requested.
        We assume the sender of the message is specified, so that the node can choose to request this block if
        it wishes to do so.
        (if it is part of a longer unknown chain, these blocks are requested as well, until reaching a known block).
        Upon receiving new blocks, they are processed and and checked for validity (check all signatures, hashes,
        block size , etc).
        If the block is on the longest chain, the mempool and utxo change accordingly.
        If the block is indeed the tip of the longest chain,
        a notification of this block is sent to the neighboring nodes of this node.
        (no need to notify of previous blocks -- the nodes will fetch them if needed)

        A reorg may be triggered by this block's introduction. In this case the utxo is rolled back to the split point,
        and then rolled forward along the new branch.
        the mempool is similarly emptied of transactions that cannot be executed now.
        transactions that were rolled back and can still be executed are re-introduced into the mempool if they do
        not conflict.
        """

        hashes = [block.get_block_hash() for block in self.blockchain]
        hashes.insert(0,GENESIS_BLOCK_PREV)

        if block_hash in hashes:
            return
        try:
            current_block = sender.get_block(block_hash)
            if current_block.get_block_hash() != block_hash:
                return

        except ValueError:
            return
        blocks_to_read = []
        # problem: what if initial hash of attacker not genesis block? answer: will catch the valueerror
        while current_block.get_prev_block_hash() not in hashes:
            blocks_to_read.append(current_block)
            try:
                a = sender.get_block(current_block.get_prev_block_hash())
                if a.get_block_hash() != current_block.get_prev_block_hash():
                    break
                current_block = a
            except ValueError:
                return
        blocks_to_read.append(current_block)
        blocks_to_read.reverse()
        # First, roll back utxo and mempool

        trial_utxo: List[Transaction] = []
        trial_txid_to_transaction: dict[TxID,Transaction] = self.txid_to_transaction
        trial_blockchain: List[Block] = []
        for block in self.blockchain[:hashes.index(current_block.get_prev_block_hash())]:
            trial_blockchain.append(block)
            for transaction in block.get_transactions():
                if transaction.input is not None:
                    trial_utxo.remove(self.txid_to_transaction[transaction.input])
                trial_utxo.append(transaction)
                trial_txid_to_transaction[transaction.get_txid()] = transaction


        # We will stop counting blocks in new blockchain when we hit an illegal block

        good_sig = lambda transaction, source_address: verify(transaction.output+transaction.input, transaction.signature, source_address)
        in_trial_utxo = lambda  transaction: trial_txid_to_transaction[transaction.input] in trial_utxo
        for block in blocks_to_read:
            if len(block.get_transactions()) > BLOCK_SIZE:
                break
            if len([t for t in block.get_transactions() if t.input is None]) != 1:
                break
            non_coinbase_tx = list(filter(lambda transaction: transaction.input is not None, block.get_transactions()))
            public_keys = [trial_txid_to_transaction[t.input].output for t in non_coinbase_tx]
            if not all(list(map(good_sig, non_coinbase_tx, public_keys))):
                break
            if not all(list(map(in_trial_utxo, non_coinbase_tx))):
                break

            trial_blockchain.append(block)
            for transaction in block.get_transactions():
                if transaction.input is not None:
                    trial_utxo.remove(trial_txid_to_transaction[transaction.input])
                trial_utxo.append(transaction)
                trial_txid_to_transaction[transaction.get_txid()] = transaction

        if len(trial_blockchain) > len(self.blockchain):
            self.blockchain = trial_blockchain
            self.txid_to_transaction = trial_txid_to_transaction
            self.mempool = list(filter(lambda transaction: trial_txid_to_transaction[transaction.input] in trial_utxo, self.mempool))
            self.utxo = trial_utxo

            self.latest_hash = self.blockchain[-1].get_block_hash()
            self.balance = [t.get_txid() for t in trial_utxo if t.output == self.publickey]
            for node in self.connections:
                node.notify_of_block(block_hash, self)


    def mine_block(self) -> BlockHash:
        """"
        This function allows the node to create a single block.
        The block should contain BLOCK_SIZE transactions (unless there aren't enough in the mempool). Of these,
        BLOCK_SIZE-1 transactions come from the mempool and one addtional transaction will be included that creates
        money and adds it to the address of this miner.
        Money creation transactions have None as their input, and instead of a signature, contain 48 random bytes.
        If a new block is created, all connections of this node are notified by calling their notify_of_block() method.
        The method returns the new block hash (or None if there was no block)
        """
        transactions = self.mempool[:BLOCK_SIZE-1]
        self.mempool = self.mempool[BLOCK_SIZE-1:]
        self.balance = [tx for tx in self.balance if tx not in [t.input for t in transactions]]
        fake_sig = Signature(secrets.token_bytes(48))
        coinbase_transaction = Transaction(self.get_address(), None, fake_sig)
        transactions.append(coinbase_transaction)
        new_block = Block(self.get_latest_hash(), transactions)
        for t in transactions:
            if t.input is not None:
                self.utxo.remove(self.txid_to_transaction[t.input])
            self.utxo.append(t)
            self.txid_to_transaction[t.get_txid()] = t
            if t.output == self.get_address():
                self.balance.append(t.get_txid())
        self.blockchain.append(new_block)
        self.latest_hash = new_block.get_block_hash()

        for node in self.connections:
            node.notify_of_block(new_block.get_block_hash(), self)
        return new_block.get_block_hash()

    def get_block(self, block_hash: BlockHash) -> Block:
        """
        This function returns a block object given its hash.
        If the block doesnt exist, a ValueError is raised.
        """
        for block in self.blockchain:
            if block.get_block_hash() == block_hash:
                return block
        raise ValueError()

    def get_latest_hash(self) -> BlockHash:
        """
        This function returns the last block hash known to this node (the tip of its current chain).
        """
        return self.latest_hash

    def get_mempool(self) -> List[Transaction]:
        """
        This function returns the list of transactions that didn't enter any block yet.
        """
        return self.mempool

    def get_utxo(self) -> List[Transaction]:
        """
        This function returns the list of unspent transactions.
        """
        return self.utxo

    # ------------ Formerly wallet methods: -----------------------

    def create_transaction(self, target: PublicKey) -> Optional[Transaction]:
        """
        This function returns a signed transaction that moves an unspent coin to the target.
        It chooses the coin based on the unspent coins that this node has.
        If the node already tried to spend a specific coin, and such a transaction exists in its mempool,
        but it did not yet get into the blockchain then it should'nt try to spend it again (until clear_mempool() is
        called -- which will wipe the mempool and thus allow to attempt these re-spends).
        The method returns None if there are no outputs that have not been spent already.

        The transaction is added to the mempool (and as a result is also published to neighboring nodes)
        """
        txid_in_mempool = [t.input for t in self.mempool]
        available_coins = [coin for coin in self.balance if coin not in txid_in_mempool]
        if not available_coins:
            return None
        new_transaction = Transaction(target, available_coins[0], sign(target+available_coins[0], self.privatekey))
        self.add_transaction_to_mempool(new_transaction)

        return new_transaction

    def clear_mempool(self) -> None:
        """
        Clears the mempool of this node. All transactions waiting to be entered into the next block are gone.
        """
        self.mempool = []

    def get_balance(self) -> int:
        """
        This function returns the number of coins that this node owns according to its view of the blockchain.
        Coins that the node owned and sent away will still be considered as part of the balance until the spending
        transaction is in the blockchain.
        """
        return len(self.balance)

    def get_address(self) -> PublicKey:
        """
        This function returns the public address of this node (its public key).
        """
        return self.publickey


"""
Importing this file should NOT execute code. It should only create definitions for the objects above.
Write any tests you have in a different file.
You may add additional methods, classes and files but be sure no to change the signatures of methods
included in this template.
"""
