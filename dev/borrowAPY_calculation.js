let supplyValue = new BigNumber(0)
let borrowInterest = new BigNumber(0)
let borrowValue = new BigNumber(0)

const _supplies = []
const _tokens = []  // Array of supplied token addresses
const _borrowAmounts =  []
const _borrowAPYs = [] // Fetched from CREAM Iron Bank
const _supplyLp = 0
const lpTokenAddress = "0x0000000000000000000000000000000000000000"

// Arrow Functions docs:
// array.forEach((element, index) => { /* ... */ })
// The .forEach method modifies each element in the array based on the given arrow (=>) function

// Get the value of tokens supplied to the pool
_supplies.forEach((s, i) => {
  const tokenPrice = priceOracle.getUsdPrice(_tokens[i])
  const tokenDecimals = IERC20.decimals(_tokens[i])
  supplyValue = supplyValue.plus(s.div(tokenDecimals).times(tokenPrice))
})

// Add the supplied LP value only if the user has supplied LP tokens
if (_supplyLp && lpTokenAddress) {
  const tokenPrice = priceOracle.getUsdPrice(lpTokenAddress)
  const tokenDecimals = IERC20.decimals(_tokens[lpTokenAddress])
  supplyValue = supplyValue.plus(_supplyLp.div(tokenDecimals).times(tokenPrice))
}

// Get the borrow value of tokens supplied to the pool
_borrowAmounts.forEach(async (borrowAmount, i) => {
  const tokenPrice = priceOracle.getUsdPrice(_tokens[i])
  const tokenDecimals = IERC20.decimals(_tokens[lpTokenAddress])

  // Add the calculated borrowValue and BorrowInterest to the global variables
  borrowValue = borrowValue.plus(borrowAmount.div(tokenDecimals).times(tokenPrice))
  borrowInterest = borrowInterest.plus(borrowAmount.div(tokenDecimals).times(tokenPrice).times(_borrowApys[i]))
})

borrowApy = borrowInterest.times(100).div(supplyValue).times(-1)