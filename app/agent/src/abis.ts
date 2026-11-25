// 필요한 함수만 적은 ABI. 형식은 API-명세.md 5절(Blockscout 검증 소스 기준)과 같다.
import { parseAbi } from "viem";

export const poolAbi = parseAbi([
  "function slot0() view returns (uint160 sqrtPriceX96, int24 tick, uint16 observationIndex, uint16 observationCardinality, uint16 observationCardinalityNext, uint8 feeProtocol, bool unlocked)",
  "function liquidity() view returns (uint128)",
  "function token0() view returns (address)",
  "function token1() view returns (address)",
  "function fee() view returns (uint24)",
  "function tickSpacing() view returns (int24)",
]);

export const npmAbi = parseAbi([
  "function positions(uint256 tokenId) view returns (uint96 nonce, address operator, address token0, address token1, uint24 fee, int24 tickLower, int24 tickUpper, uint128 liquidity, uint256 feeGrowthInside0LastX128, uint256 feeGrowthInside1LastX128, uint128 tokensOwed0, uint128 tokensOwed1)",
  "function ownerOf(uint256 tokenId) view returns (address)",
  "function balanceOf(address owner) view returns (uint256)",
  "function tokenOfOwnerByIndex(address owner, uint256 index) view returns (uint256)",
  "function factory() view returns (address)",
]);

export const factoryAbi = parseAbi([
  "function getPool(address tokenA, address tokenB, uint24 fee) view returns (address)",
]);

export const supraPullAbi = [
  {
    type: "function",
    name: "verifyOracleProofV2",
    stateMutability: "nonpayable",
    inputs: [{ name: "_bytesProof", type: "bytes" }],
    outputs: [
      {
        name: "",
        type: "tuple",
        components: [
          { name: "pairs", type: "uint256[]" },
          { name: "prices", type: "uint256[]" },
          { name: "timestamp", type: "uint256[]" },
          { name: "decimal", type: "uint256[]" },
          { name: "round", type: "uint256[]" },
        ],
      },
    ],
  },
] as const;
