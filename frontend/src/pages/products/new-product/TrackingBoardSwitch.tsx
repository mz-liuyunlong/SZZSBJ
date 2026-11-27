/** This switch leaves the already-finished New Product board completely untouched. */
import type { ComponentProps } from 'react';
import NativeBoard from './NativeBoardFacade';
import TrackingDashboard from './TrackingDashboard';
import type { TrackingDrillFilter } from './trackingBoardDrilldown';

type Props = ComponentProps<typeof NativeBoard> & { onTrackingDrill?: (filter:TrackingDrillFilter)=>void };
export default function TrackingBoardSwitch(props:Props){
  return props.mode==='tracking'
    ? <TrackingDashboard products={props.products} config={props.config} onDrill={props.onTrackingDrill ?? (()=>props.detail())}/>
    : <NativeBoard {...props}/>;
}
