from kairon.shared.cognition.data_objects import CollectionData



class DataProcessor:

    @staticmethod
    def get_all_collections(bot: str):
        pipeline = [
                    {"$match": {"bot": bot}},
                    {"$group": {"_id": "$collection_name", "count": {"$sum": 1}}},
                    {"$project": {"collection_name": "$_id", "count": 1, "_id": 0}}
            ]
        result = list(CollectionData.objects(bot=bot).aggregate(pipeline))

        return result

    @staticmethod
    def delete_collection(bot: str, name: str):
        result = CollectionData.objects(bot=bot, collection_name=name).delete()
        if result > 0:
            message = f"Collection {name} deleted successfully!"
        else:
            message = f"Collection {name} does not exist!"
        return [message, result]





