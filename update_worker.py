import fetch_blocks
import analysis
import main_mev
import chartprep

if __name__ == "__main__":
    # update the website everyday, but always only show 14 days of results
    # get the last 14 days of data
    two_weeks_blocks = 2000  # 14 * 24 * 60 * 60 / 12
    # start_block = 18088050
    start_block = fetch_blocks.block_number_14_days_ago()
    print(start_block)

    # fetched_blocks = fetch_blocks.get_blocks(start_block, two_weeks_blocks)
    # analysis.dump_dict_to_json(fetched_blocks, "fourteen_blocks.json")

    # fetched_internal_transfers = (
    #     fetch_blocks.get_internal_transfers_to_fee_recipients_in_blocks(fetched_blocks)
    # )
    # analysis.dump_dict_to_json(fetched_internal_transfers, "fourteen_transfers.json")

    # fetched_receipts = fetch_blocks.get_blocks_receipts(start_block, two_weeks_blocks)
    # analysis.dump_dict_to_json(fetched_receipts, "fourteen_receipts.json")

    fetched_blocks = analysis.load_dict_from_json("fourteen_blocks.json")
    fetched_internal_transfers = analysis.load_dict_from_json("fourteen_transfers.json")

    main_mev.create_mev_analysis(fetched_blocks, fetched_internal_transfers)

    # update the charts
    chartprep.create_html_page()
