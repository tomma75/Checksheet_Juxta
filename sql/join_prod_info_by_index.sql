SELECT 
    a.PROD_NO,
    a.PROD_INST_SHEET_REV_NO,
    a.PROD_INST_REV_NO,
    a.PROD_ITEM_REV_NO,
    a.ORDER_NO,
    a.ITEM_NO,
    a.SERIAL_NO,
    a.INDEX_NO,
    a.INDEX_NO_SFIX,
    NVL(TO_CHAR(a.START_NO), 'null') AS START_NO,
    b.ORDER_ENTRY_CODE,
    b.MS_CODE,
    b.MODEL,
    b.CHK_SUFFIX_CODE,
    b.CHK_OPT_CODE,
    TO_CHAR(c.ENTRY_D, 'DD') || '-' || LPAD(c.SEQ, 3, '0') AS SEQ
FROM 
    TDSC952 a
JOIN 
    TDSC951 b ON a.PROD_NO = b.PROD_NO 
               AND a.PROD_INST_SHEET_REV_NO = b.PROD_INST_SHEET_REV_NO
               AND a.PROD_INST_REV_NO = b.PROD_INST_REV_NO
               AND a.PROD_ITEM_REV_NO = b.PROD_ITEM_REV_NO
               AND a.ORDER_NO = b.ORDER_NO
               AND a.ITEM_NO = b.ITEM_NO
               AND b.CANCEL_D IS NULL
LEFT JOIN
    PDSD0010 c ON a.PROD_NO = c.PROD_NO
WHERE 
    a.INDEX_NO = '{index_no}'
    AND a.INDEX_NO_SFIX = '{index_no_sfix}'