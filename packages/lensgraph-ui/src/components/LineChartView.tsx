/**
 * A cited `LineChart` drawn with MUI X Charts (community): one line per series over a date
 * x-axis, with legend and tooltip. Generic: it knows nothing about what the series mean.
 * See documentation/design/core.md, Reporting: run view.
 */
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import { LineChart as MuiLineChart } from "@mui/x-charts/LineChart";
import type { LineChart } from "../types/run-view";

/** Draw `chart`: gaps (null y values) break the line; colours come from the MUI theme palette. */
export function LineChartView({ chart }: { chart: LineChart }) {
  const theme = useTheme();
  const colors = [
    theme.palette.primary.main,
    theme.palette.secondary.main,
    theme.palette.success.main,
    theme.palette.warning.main,
    theme.palette.error.main,
    theme.palette.info.main,
  ];
  return (
    <Box>
      <Typography variant="subtitle2">{chart.title}</Typography>
      <MuiLineChart
        height={300}
        colors={colors}
        xAxis={[{ scaleType: "time", data: chart.x.map((d) => new Date(d)) }]}
        yAxis={[{ label: chart.y_label ?? undefined }]}
        series={Object.entries(chart.series).map(([name, data]) => ({
          id: name,
          label: name,
          data,
          showMark: false,
          connectNulls: false,
        }))}
      />
    </Box>
  );
}
