# Simple Blockchain Simulation

This project simulates a decentralized crypto mining network, with two notable simplifications. 
Firstly, unlike in real cryptocurrencies, each transaction represents 1 coin that cannot be divided. 
Secondly, miners do not mine blocks based on proof of work. Instead, an external call (by the test script, for example) will notify a node that its turn to create a block has arrived.

This simulation uses a UTxO model. Meaning, each transaction (which represents 1 indivisible coin) "points" to the previous transaction from whence it came, unless it's a coinbase transaction, in which case it has no such pointer. Each block holds a bunch of transactions. 
Each node represents a miner in the network. Nodes notify each other of the tip of their blockchain when they connect with each other, and once connected, notify each other of new transactions to arrive in their mempool (provided it doesn't double spend a transaction already in the mempool), and of new blocks each time they mine/receive a new one. 
Before accepting and propagating new blocks, each node checks that all transactions in the new block are valid, and that the block isn't malformed (otherwise the block is discarded). 
Upon receiving a new block, if it doesn't point to the hash of the last block in the node's chain, the node asks for blocks until reaching a recognized intersection or the genesis block (assuming all the blocks are validated). At that point, the node adopts the new chain if it's longer, and otherwise discards it. If adopted, the node does a chain-reorg, updating its UTxO and mempool accordingly.
