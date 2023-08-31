/* Database */

CREATE DATABASE `Enphase`;
USE `Enphase`;

/* Tables */

CREATE TABLE `MeterReading_Result` (
 `ResultID` INT          UNSIGNED NOT NULL AUTO_INCREMENT,
 `p`        DECIMAL(9,3)          NOT NULL COMMENT 'wNow',
 `q`        DECIMAL(9,3)          NOT NULL COMMENT 'reactPwr',
 `s`        DECIMAL(9,3)          NOT NULL COMMENT 'apprntPwr',
 `v`        DECIMAL(6,3) UNSIGNED NOT NULL COMMENT 'rmsVoltage',
 `i`        DECIMAL(5,3)          NOT NULL COMMENT 'rmsCurrent',
 `pf`       DECIMAL(3,2)          NOT NULL COMMENT 'pwrFactor',
 `f`        DECIMAL(4,2) UNSIGNED NOT NULL COMMENT 'frequency',
 PRIMARY KEY (`ResultID`)
);

CREATE TABLE `MeterReading` (
 `ReadingID`                   INT       UNSIGNED NOT NULL AUTO_INCREMENT,
 `Timestamp`                   TIMESTAMP          NOT NULL DEFAULT CURRENT_TIMESTAMP,
 `Production_Phase_A_ID`       INT       UNSIGNED NULL,
 `Production_Phase_B_ID`       INT       UNSIGNED NULL,
 `Production_Phase_C_ID`       INT       UNSIGNED NULL,
 `NetConsumption_Phase_A_ID`   INT       UNSIGNED NULL,
 `NetConsumption_Phase_B_ID`   INT       UNSIGNED NULL,
 `NetConsumption_Phase_C_ID`   INT       UNSIGNED NULL,
 `TotalConsumption_Phase_A_ID` INT       UNSIGNED NULL,
 `TotalConsumption_Phase_B_ID` INT       UNSIGNED NULL,
 `TotalConsumption_Phase_C_ID` INT       UNSIGNED NULL,
  CONSTRAINT `MeterReading_Production_Phase_A_ID`       FOREIGN KEY (`Production_Phase_A_ID`)       REFERENCES `MeterReading_Result` (`ResultID`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `MeterReading_Production_Phase_B_ID`       FOREIGN KEY (`Production_Phase_B_ID`)       REFERENCES `MeterReading_Result` (`ResultID`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `MeterReading_Production_Phase_C_ID`       FOREIGN KEY (`Production_Phase_C_ID`)       REFERENCES `MeterReading_Result` (`ResultID`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `MeterReading_NetConsumption_Phase_A_ID`   FOREIGN KEY (`NetConsumption_Phase_A_ID`)   REFERENCES `MeterReading_Result` (`ResultID`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `MeterReading_NetConsumption_Phase_B_ID`   FOREIGN KEY (`NetConsumption_Phase_B_ID`)   REFERENCES `MeterReading_Result` (`ResultID`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `MeterReading_NetConsumption_Phase_C_ID`   FOREIGN KEY (`NetConsumption_Phase_C_ID`)   REFERENCES `MeterReading_Result` (`ResultID`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `MeterReading_TotalConsumption_Phase_A_ID` FOREIGN KEY (`TotalConsumption_Phase_A_ID`) REFERENCES `MeterReading_Result` (`ResultID`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `MeterReading_TotalConsumption_Phase_B_ID` FOREIGN KEY (`TotalConsumption_Phase_B_ID`) REFERENCES `MeterReading_Result` (`ResultID`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `MeterReading_TotalConsumption_Phase_C_ID` FOREIGN KEY (`TotalConsumption_Phase_C_ID`) REFERENCES `MeterReading_Result` (`ResultID`) ON DELETE CASCADE ON UPDATE CASCADE,
 PRIMARY KEY (`ReadingID`)
);

/* Views */

CREATE
SQL SECURITY INVOKER
VIEW `MeterReading_TriplePhase_View`
AS
SELECT
 ReadingID,
 Timestamp,

 Production_Phase_A.p AS 'Production_Phase_A_p',
 Production_Phase_A.q AS 'Production_Phase_A_q',
 Production_Phase_A.s AS 'Production_Phase_A_s',
 Production_Phase_A.v AS 'Production_Phase_A_v',
 Production_Phase_A.i AS 'Production_Phase_A_i',
 Production_Phase_A.pf AS 'Production_Phase_A_pf',
 Production_Phase_A.f AS 'Production_Phase_A_f',

 Production_Phase_B.p AS 'Production_Phase_B_p',
 Production_Phase_B.q AS 'Production_Phase_B_q',
 Production_Phase_B.s AS 'Production_Phase_B_s',
 Production_Phase_B.v AS 'Production_Phase_B_v',
 Production_Phase_B.i AS 'Production_Phase_B_i',
 Production_Phase_B.pf AS 'Production_Phase_B_pf',
 Production_Phase_B.f AS 'Production_Phase_B_f',

 Production_Phase_C.p AS 'Production_Phase_C_p',
 Production_Phase_C.q AS 'Production_Phase_C_q',
 Production_Phase_C.s AS 'Production_Phase_C_s',
 Production_Phase_C.v AS 'Production_Phase_C_v',
 Production_Phase_C.i AS 'Production_Phase_C_i',
 Production_Phase_C.pf AS 'Production_Phase_C_pf',
 Production_Phase_C.f AS 'Production_Phase_C_f',

 NetConsumption_Phase_A.p AS 'NetConsumption_Phase_A_p',
 NetConsumption_Phase_A.q AS 'NetConsumption_Phase_A_q',
 NetConsumption_Phase_A.s AS 'NetConsumption_Phase_A_s',
 NetConsumption_Phase_A.v AS 'NetConsumption_Phase_A_v',
 NetConsumption_Phase_A.i AS 'NetConsumption_Phase_A_i',
 NetConsumption_Phase_A.pf AS 'NetConsumption_Phase_A_pf',
 NetConsumption_Phase_A.f AS 'NetConsumption_Phase_A_f',

 NetConsumption_Phase_B.p AS 'NetConsumption_Phase_B_p',
 NetConsumption_Phase_B.q AS 'NetConsumption_Phase_B_q',
 NetConsumption_Phase_B.s AS 'NetConsumption_Phase_B_s',
 NetConsumption_Phase_B.v AS 'NetConsumption_Phase_B_v',
 NetConsumption_Phase_B.i AS 'NetConsumption_Phase_B_i',
 NetConsumption_Phase_B.pf AS 'NetConsumption_Phase_B_pf',
 NetConsumption_Phase_B.f AS 'NetConsumption_Phase_B_f',

 NetConsumption_Phase_C.p AS 'NetConsumption_Phase_C_p',
 NetConsumption_Phase_C.q AS 'NetConsumption_Phase_C_q',
 NetConsumption_Phase_C.s AS 'NetConsumption_Phase_C_s',
 NetConsumption_Phase_C.v AS 'NetConsumption_Phase_C_v',
 NetConsumption_Phase_C.i AS 'NetConsumption_Phase_C_i',
 NetConsumption_Phase_C.pf AS 'NetConsumption_Phase_C_pf',
 NetConsumption_Phase_C.f AS 'NetConsumption_Phase_C_f',

 TotalConsumption_Phase_A.p AS 'TotalConsumption_Phase_A_p',
 TotalConsumption_Phase_A.q AS 'TotalConsumption_Phase_A_q',
 TotalConsumption_Phase_A.s AS 'TotalConsumption_Phase_A_s',
 TotalConsumption_Phase_A.v AS 'TotalConsumption_Phase_A_v',
 TotalConsumption_Phase_A.i AS 'TotalConsumption_Phase_A_i',
 TotalConsumption_Phase_A.pf AS 'TotalConsumption_Phase_A_pf',
 TotalConsumption_Phase_A.f AS 'TotalConsumption_Phase_A_f',

 TotalConsumption_Phase_B.p AS 'TotalConsumption_Phase_B_p',
 TotalConsumption_Phase_B.q AS 'TotalConsumption_Phase_B_q',
 TotalConsumption_Phase_B.s AS 'TotalConsumption_Phase_B_s',
 TotalConsumption_Phase_B.v AS 'TotalConsumption_Phase_B_v',
 TotalConsumption_Phase_B.i AS 'TotalConsumption_Phase_B_i',
 TotalConsumption_Phase_B.pf AS 'TotalConsumption_Phase_B_pf',
 TotalConsumption_Phase_B.f AS 'TotalConsumption_Phase_B_f',

 TotalConsumption_Phase_C.p AS 'TotalConsumption_Phase_C_p',
 TotalConsumption_Phase_C.q AS 'TotalConsumption_Phase_C_q',
 TotalConsumption_Phase_C.s AS 'TotalConsumption_Phase_C_s',
 TotalConsumption_Phase_C.v AS 'TotalConsumption_Phase_C_v',
 TotalConsumption_Phase_C.i AS 'TotalConsumption_Phase_C_i',
 TotalConsumption_Phase_C.pf AS 'TotalConsumption_Phase_C_pf',
 TotalConsumption_Phase_C.f AS 'TotalConsumption_Phase_C_f'

FROM MeterReading
LEFT JOIN MeterReading_Result Production_Phase_A ON MeterReading.Production_Phase_A_ID = Production_Phase_A.ResultID
LEFT JOIN MeterReading_Result Production_Phase_B ON MeterReading.Production_Phase_B_ID = Production_Phase_B.ResultID
LEFT JOIN MeterReading_Result Production_Phase_C ON MeterReading.Production_Phase_C_ID = Production_Phase_C.ResultID

LEFT JOIN MeterReading_Result NetConsumption_Phase_A ON MeterReading.NetConsumption_Phase_A_ID = NetConsumption_Phase_A.ResultID
LEFT JOIN MeterReading_Result NetConsumption_Phase_B ON MeterReading.NetConsumption_Phase_B_ID = NetConsumption_Phase_B.ResultID
LEFT JOIN MeterReading_Result NetConsumption_Phase_C ON MeterReading.NetConsumption_Phase_C_ID = NetConsumption_Phase_C.ResultID

LEFT JOIN MeterReading_Result TotalConsumption_Phase_A ON MeterReading.TotalConsumption_Phase_A_ID = TotalConsumption_Phase_A.ResultID
LEFT JOIN MeterReading_Result TotalConsumption_Phase_B ON MeterReading.TotalConsumption_Phase_B_ID = TotalConsumption_Phase_B.ResultID
LEFT JOIN MeterReading_Result TotalConsumption_Phase_C ON MeterReading.TotalConsumption_Phase_C_ID = TotalConsumption_Phase_C.ResultID
ORDER BY ReadingID DESC;

CREATE
SQL SECURITY INVOKER
VIEW `MeterReading_SinglePhase_View`
AS
SELECT
 ReadingID,
 Timestamp,
 Production_Phase_A.p AS 'Production_p',
 Production_Phase_A.q AS 'Production_q',
 Production_Phase_A.s AS 'Production_s',
 Production_Phase_A.v AS 'Production_v',
 Production_Phase_A.i AS 'Production_i',
 Production_Phase_A.pf AS 'Production_pf',
 Production_Phase_A.f AS 'Production_f',

 NetConsumption_Phase_A.p AS 'NetConsumption_p',
 NetConsumption_Phase_A.q AS 'NetConsumption_q',
 NetConsumption_Phase_A.s AS 'NetConsumption_s',
 NetConsumption_Phase_A.v AS 'NetConsumption_v',
 NetConsumption_Phase_A.i AS 'NetConsumption_i',
 NetConsumption_Phase_A.pf AS 'NetConsumption_pf',
 NetConsumption_Phase_A.f AS 'NetConsumption_f',

 TotalConsumption_Phase_A.p AS 'TotalConsumption_p',
 TotalConsumption_Phase_A.q AS 'TotalConsumption_q',
 TotalConsumption_Phase_A.s AS 'TotalConsumption_s',
 TotalConsumption_Phase_A.v AS 'TotalConsumption_v',
 TotalConsumption_Phase_A.i AS 'TotalConsumption_i',
 TotalConsumption_Phase_A.pf AS 'TotalConsumption_pf',
 TotalConsumption_Phase_A.f AS 'TotalConsumption_f'

FROM MeterReading
LEFT JOIN MeterReading_Result Production_Phase_A       ON MeterReading.Production_Phase_A_ID = Production_Phase_A.ResultID
LEFT JOIN MeterReading_Result NetConsumption_Phase_A   ON MeterReading.NetConsumption_Phase_A_ID = NetConsumption_Phase_A.ResultID
LEFT JOIN MeterReading_Result TotalConsumption_Phase_A ON MeterReading.TotalConsumption_Phase_A_ID = TotalConsumption_Phase_A.ResultID
ORDER BY ReadingID DESC;

/*
  This view includes fields which help with financial calculations:
  - You may wish to uncomment `Cost (£)` and `Saved (£)` and replace '32.79' with your energy import cost.
  - You may wish to uncomment `SEG Value (£)` and replace '12' with your energy export rate.
*/

CREATE
SQL SECURITY INVOKER
VIEW `MeterReading_Statistics_View`
AS
SELECT DATE(Timestamp) AS 'Date',
       ROUND(  ((SUM(CASE WHEN NetConsumption_P >= 0 THEN NetConsumption_P ELSE 0 END) / COUNT(*)) * COUNT(DISTINCT HOUR(Timestamp))) / 1000, 2) AS `Import (kWh)`,
       -- ROUND(((((SUM(CASE WHEN NetConsumption_P >= 0 THEN NetConsumption_P ELSE 0 END) / COUNT(*)) * COUNT(DISTINCT HOUR(Timestamp))) / 1000) * 32.79) / 100, 2) AS `Cost (£)`,
       ROUND(((SUM(Production_P) / COUNT(*)) * COUNT(DISTINCT HOUR(Timestamp))) / 1000, 2) AS `Produced (kWh)`,
       ROUND(((SUM(TotalConsumption_P) / COUNT(*)) * COUNT(DISTINCT HOUR(Timestamp))) / 1000, 2) AS `Consumed (kWh)`,
       ROUND(  (((SUM(TotalConsumption_P) - SUM(CASE WHEN NetConsumption_P >= 0 THEN NetConsumption_P ELSE 0 END)) / COUNT(*)) * COUNT(DISTINCT HOUR(Timestamp))) / 1000, 2) AS `Self Consumed (kWh)`,
       -- ROUND((((((SUM(TotalConsumption_P) - SUM(CASE WHEN NetConsumption_P >= 0 THEN NetConsumption_P ELSE 0 END)) / COUNT(*)) * COUNT(DISTINCT HOUR(Timestamp))) / 1000) * 32.79) / 100, 2) AS `Saved (£)`,
       ROUND(((SUM(CASE WHEN NetConsumption_P < 0 THEN ABS(NetConsumption_P) ELSE 0 END) / COUNT(*)) * COUNT(DISTINCT HOUR(Timestamp))) / 1000, 2) AS `Export (kWh)`,
       ROUND(((SUM(NetConsumption_P) / COUNT(*)) * COUNT(DISTINCT HOUR(Timestamp))) / 1000, 2) AS `Net Import/Export (kWh)`,
       -- ROUND((((SUM(CASE WHEN NetConsumption_P < 0 THEN ABS(NetConsumption_P) ELSE 0 END) / COUNT(*)) * COUNT(DISTINCT HOUR(Timestamp)) / 1000) * 12) / 100, 2) AS `SEG Value (£)`,
       TIME_FORMAT(SEC_TO_TIME(COUNT(*)),'%Hh %im') AS `Duration`
FROM MeterReading_SinglePhase_View
GROUP BY DATE(Timestamp)
ORDER BY `Produced (kWh)` DESC;