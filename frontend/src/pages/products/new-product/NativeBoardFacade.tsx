/** PR337_PERFORMANCE_BOARD_V6 - keep tracking view in original NativeBoard. */
import type { ComponentProps } from "react";
import NativeBoardOriginal from "./NativeBoard";
import PerformanceBoardRedesign from "./PerformanceBoardRedesign";

type Props = ComponentProps<typeof NativeBoardOriginal>;

export default function NativeBoardFacade(props: Props) {
  if (props.mode === "performance") {
    return <PerformanceBoardRedesign products={props.products} config={props.config} detail={props.detail} open={props.open}/>;
  }
  return <NativeBoardOriginal {...props}/>;
}
